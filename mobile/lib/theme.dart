import 'package:flutter/material.dart';

/// Same tokens as `webui/src/styles/base.css`, translated once.
///
/// Two clients that disagree on "danger" red make screenshots from a support call
/// ambiguous, so the values are copied rather than invented.
const brand = Color(0xFF1D4ED8);
const brandDark = Color(0xFF1A44BD);
const bg = Color(0xFFF4F6FA);
const surface = Color(0xFFFFFFFF);
const surface2 = Color(0xFFFAFBFD);
const ink = Color(0xFF0F172A);
const ink2 = Color(0xFF334155);
const ink3 = Color(0xFF5B6B84);
const border = Color(0xFFE1E7F0);
const warn = Color(0xFFB45309);
const warnSoft = Color(0xFFFFF9ED);
const danger = Color(0xFFB42318);
const dangerSoft = Color(0xFFFEF4F2);

ThemeData buildTheme() {
  final base = ThemeData(
    useMaterial3: true,
    colorScheme: ColorScheme.fromSeed(
      seedColor: brand,
      brightness: Brightness.light,
      surface: surface,
    ),
  );
  return base.copyWith(
    scaffoldBackgroundColor: bg,
    appBarTheme: const AppBarTheme(
      backgroundColor: surface,
      foregroundColor: ink,
      elevation: 0,
      centerTitle: false,
      titleTextStyle: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, color: ink),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: surface2,
      isDense: true,
      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(10),
        borderSide: const BorderSide(color: brand, width: 1.6),
      ),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: brand,
        minimumSize: const Size.fromHeight(46),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    ),
    snackBarTheme: const SnackBarThemeData(behavior: SnackBarBehavior.floating),
  );
}
