//! Desktop shell for the soapbot control panel.
//!
//! Two ways to run, one rule: never two backends on one port.
//!
//! * **Supervised** — installs made by `scripts/install.ps1` or `scripts/install.sh`
//!   hand the process to Task Scheduler / systemd. The shell probes the port and only
//!   connects; starting a second copy would either fail to bind or win the race and
//!   leave the supervised copy dead, unreachable by any restart command.
//! * **Self-hosted** — a bare machine running the desktop bundle. Nothing is listening
//!   and a `soapbot-backend` executable sits beside the shell, so the shell spawns it
//!   and kills it on exit.
//!
//! The decision is `spawn_decision`, a pure function with unit tests, because the rest
//! of the lifecycle needs a GUI and a real backend to exercise. Order matters and is
//! encoded there: **probe first, spawn second**.
//!
//! Killing needs the whole tree, not the direct child: PyInstaller's onefile bootloader
//! forks the interpreter, so `Child::kill` leaves the real server alive holding the
//! port. Measured on Windows while packaging the sidecar: the spawned pid was gone and
//! `soapbot-backend` was still in the process list.

use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::Duration;

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager, RunEvent};

/// Where the panel listens. Matches `Settings.port` in the Python config; the CSP in
/// `tauri.conf.json` names the same origin, so the two cannot drift silently.
const PANEL_URL: &str = "http://127.0.0.1:6185";
const PANEL_ADDR: &str = "127.0.0.1:6185";

/// Event the shell page listens for, so the tray can hand it a command to copy.
///
/// An event rather than `webview.eval("navigator.clipboard.writeText(...)")`: the
/// command embeds a service name that comes from the environment, and interpolating it
/// into evaluated JavaScript is a string-injection path for no benefit.
const COPY_EVENT: &str = "soapbot://copy-restart";

/// The frozen backend produced by `desktop/sidecar/build.py`.
const SIDECAR: &str = if cfg!(windows) {
    "soapbot-backend.exe"
} else {
    "soapbot-backend"
};

/// How long the probe waits for a TCP handshake. Local loopback answers in microseconds
/// or not at all; a longer budget only delays the window on a machine where nothing runs.
const PROBE_TIMEOUT: Duration = Duration::from_millis(300);

/// Owns the child this shell started, if any.
struct Backend(Mutex<Option<Child>>);

#[derive(Debug, PartialEq, Eq)]
enum SpawnDecision {
    /// Something already answers on the port; do not start a second one.
    AlreadyRunning,
    /// No listener and no binary: show the operator how to install the service.
    NoSidecar,
    /// No listener, binary present: this shell owns the lifecycle.
    Spawn,
}

fn spawn_decision(port_open: bool, sidecar_present: bool) -> SpawnDecision {
    if port_open {
        SpawnDecision::AlreadyRunning
    } else if sidecar_present {
        SpawnDecision::Spawn
    } else {
        SpawnDecision::NoSidecar
    }
}

fn port_open(addr: &str, timeout: Duration) -> bool {
    match addr.parse() {
        Ok(socket) => std::net::TcpStream::connect_timeout(&socket, timeout).is_ok(),
        // An unparsable address is a closed port from this shell's point of view: the
        // fallback is the "no backend" page, which is the safe side of the decision.
        Err(_) => false,
    }
}

/// Places the sidecar may live, most specific first.
fn sidecar_candidates(app: &tauri::AppHandle) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            // Installed bundle: both binaries in one folder.
            out.push(dir.join(SIDECAR));
        }
    }
    if let Ok(dir) = app.path().resource_dir() {
        // Tauri resource layout used by `bundle.resources`.
        out.push(dir.join("binaries").join(SIDECAR));
        out.push(dir.join(SIDECAR));
    }
    out
}

fn find_sidecar(app: &tauri::AppHandle) -> Option<PathBuf> {
    sidecar_candidates(app).into_iter().find(|path| path.is_file())
}

fn start_sidecar(path: &Path) -> std::io::Result<Child> {
    Command::new(path)
        // Detached from the shell's own pipes: the backend writes structured logs to
        // its data directory, and a GUI-launched process has nowhere to put a console.
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
}

fn stop_backend(child: &mut Child) {
    let pid = child.id().to_string();
    #[cfg(windows)]
    {
        // `/T` is the whole point: the onefile bootloader's interpreter is a child.
        let _ = Command::new("taskkill")
            .args(["/PID", &pid, "/T", "/F"])
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
    #[cfg(not(windows))]
    {
        let _ = child.kill();
    }
    let _ = child.wait();
}

fn stop_owned_backend(app: &tauri::AppHandle) {
    let Some(state) = app.try_state::<Backend>() else {
        return;
    };
    let Ok(mut guard) = state.0.lock() else {
        return;
    };
    // `take()` makes this idempotent: `ExitRequested` and `Exit` both arrive, and
    // killing an already-reaped pid would fail loudly for no reason.
    if let Some(mut child) = guard.take() {
        stop_backend(&mut child);
    }
}

fn focus_main(app: &tauri::AppHandle) {
    if let Some(window) = app.get_webview_window("main") {
        let _ = window.show();
        let _ = window.unminimize();
        let _ = window.set_focus();
    }
}

/// The same three-way split as `src/soapbot/api/service_hint.py`.
fn restart_command() -> String {
    if std::path::Path::new("/.dockerenv").exists() {
        return "docker compose restart soapbot".into();
    }
    let fallback = if cfg!(windows) { "SoapbotBot" } else { "soapbot" };
    let name = std::env::var("SOAPBOT_SERVICE_NAME")
        .ok()
        .map(|value| value.trim().to_string())
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| fallback.into());
    if cfg!(windows) {
        format!("schtasks /End /TN {name} && schtasks /Run /TN {name}")
    } else {
        format!("systemctl restart {name}")
    }
}

fn build_tray(app: &tauri::AppHandle) -> tauri::Result<()> {
    let open = MenuItem::with_id(app, "open", "打开控制台", true, None::<&str>)?;
    let copy = MenuItem::with_id(app, "copy", "复制重启命令", true, None::<&str>)?;
    let quit = MenuItem::with_id(app, "quit", "退出", true, None::<&str>)?;
    let separator = PredefinedMenuItem::separator(app)?;
    let menu = Menu::with_items(app, &[&open, &copy, &separator, &quit])?;

    let Some(icon) = app.default_window_icon().cloned() else {
        // No icon means no tray on Windows. Losing the tray is survivable; panicking at
        // startup over a missing asset is not, because the window would never appear.
        eprintln!("soapbot: default window icon missing, tray disabled");
        return Ok(());
    };

    TrayIconBuilder::with_id("soapbot")
        .tooltip("soapbot 控制台")
        .icon(icon)
        .menu(&menu)
        // Left click opens the panel; the menu stays on right click. Making the left
        // click open a menu instead is the behaviour nobody expects from a tray icon.
        .show_menu_on_left_click(false)
        .on_menu_event(|app, event| match event.id().as_ref() {
            "open" => focus_main(app),
            "copy" => {
                focus_main(app);
                let _ = app.emit(COPY_EVENT, restart_command());
            }
            "quit" => app.exit(0),
            _ => {}
        })
        .on_tray_icon_event(|tray, event| {
            if let TrayIconEvent::Click {
                button: MouseButton::Left,
                button_state: MouseButtonState::Up,
                ..
            } = event
            {
                focus_main(tray.app_handle());
            }
        })
        .build(app)?;
    Ok(())
}

fn main() {
    let app = tauri::Builder::default()
        // Registered first on purpose: the plugin runs its callback during `setup`, and
        // a second launch must focus the existing window instead of opening a duplicate.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            focus_main(app);
        }))
        .setup(|app| {
            build_tray(app.handle())?;

            let listening = port_open(PANEL_ADDR, PROBE_TIMEOUT);
            let sidecar = find_sidecar(app.handle());
            match spawn_decision(listening, sidecar.is_some()) {
                SpawnDecision::AlreadyRunning => {
                    println!("soapbot: backend already listening on {PANEL_ADDR}");
                }
                SpawnDecision::NoSidecar => {
                    println!(
                        "soapbot: nothing on {PANEL_ADDR} and no {SIDECAR} beside the shell"
                    );
                }
                SpawnDecision::Spawn => {
                    let path = sidecar.expect("SpawnDecision::Spawn implies a path");
                    match start_sidecar(&path) {
                        Ok(child) => {
                            app.manage(Backend(Mutex::new(Some(child))));
                        }
                        Err(err) => {
                            eprintln!("soapbot: could not start {}: {err}", path.display());
                        }
                    }
                }
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![panel_url, restart_hint])
        .build(tauri::generate_context!())
        .expect("failed to start the soapbot desktop shell");

    app.run(|handle, event| {
        if matches!(event, RunEvent::ExitRequested { .. } | RunEvent::Exit) {
            stop_owned_backend(handle);
        }
    });
}

/// The panel origin, so the local page never hardcodes a port.
#[tauri::command]
fn panel_url() -> &'static str {
    PANEL_URL
}

/// The command to show when the probe fails.
#[tauri::command]
fn restart_hint() -> String {
    restart_command()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn a_listening_port_is_never_started_again() {
        assert_eq!(spawn_decision(true, true), SpawnDecision::AlreadyRunning);
        assert_eq!(spawn_decision(true, false), SpawnDecision::AlreadyRunning);
    }

    #[test]
    fn a_missing_binary_does_not_fake_a_backend() {
        assert_eq!(spawn_decision(false, false), SpawnDecision::NoSidecar);
    }

    #[test]
    fn an_idle_port_with_a_sidecar_becomes_ours() {
        assert_eq!(spawn_decision(false, true), SpawnDecision::Spawn);
    }

    #[test]
    fn an_unparsable_address_reads_as_closed() {
        assert!(!port_open("not-a-socket", Duration::from_millis(10)));
    }

    #[test]
    fn a_closed_port_reads_as_closed() {
        // Port 1 on loopback is never a soapbot backend.
        assert!(!port_open("127.0.0.1:1", Duration::from_millis(50)));
    }
}
