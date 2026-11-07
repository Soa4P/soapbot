//! Desktop shell for the soapbot control panel.
//!
//! What this deliberately does **not** do: start the Python backend. On Windows the
//! backend is a scheduled task (`SoapbotBot`) and on Linux a systemd unit, both of which
//! already own the process lifecycle. A shell that also spawned a child would produce
//! two servers racing for port 6185, and the loser would fail with a bind error the
//! operator never asked to debug.
//!
//! So the shell is a window plus a probe. The window loads its own small document
//! (`ui/index.html`), which asks `/api/health` and either hands the webview over to the
//! real panel or renders the local "backend is not running" page with the exact command
//! for this platform. The probe lives in the page rather than here because it needs to
//! be re-runnable from a button, and because a Rust HTTP client would be one more crate
//! for one GET.

use tauri::menu::{Menu, MenuItem, PredefinedMenuItem};
use tauri::tray::{MouseButton, MouseButtonState, TrayIconBuilder, TrayIconEvent};
use tauri::{Emitter, Manager};

/// Where the panel listens. Matches `Settings.port` in the Python config; the CSP in
/// `tauri.conf.json` names the same origin, so the two cannot drift silently.
const PANEL_URL: &str = "http://127.0.0.1:6185";

/// Event the shell page listens for, so the tray can hand it a command to copy.
///
/// An event rather than `webview.eval("navigator.clipboard.writeText(...)")`: the
/// command embeds a service name that comes from the environment, and interpolating it
/// into evaluated JavaScript is a string-injection path for no benefit.
const COPY_EVENT: &str = "soapbot://copy-restart";

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
    tauri::Builder::default()
        // Registered first on purpose: the plugin runs its callback during `setup`, and
        // a second launch must focus the existing window instead of opening a duplicate.
        .plugin(tauri_plugin_single_instance::init(|app, _argv, _cwd| {
            focus_main(app);
        }))
        .setup(|app| {
            build_tray(app.handle())?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![panel_url, restart_hint])
        .run(tauri::generate_context!())
        .expect("failed to start the soapbot desktop shell");
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
