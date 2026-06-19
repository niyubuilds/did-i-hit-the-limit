#!/usr/bin/env python3
"""Shared title-bar overlay UI for truHue usage bars (Claude, Codex, …).

The panel FOLLOWS its target app's window (winbounds, via CoreGraphics), parking
at a saved offset from the window's top-right corner. It auto-sizes to its text,
shows only while the app is frontmost, and can be dragged to reposition (the new
offset is remembered). Right-click → Refresh / Quit.

run(cfg) keys:
    name, bundle_id, owner, fetch, render, poll_seconds
    right_extra   default left-shift from the right edge (px), e.g. to clear buttons
    offset_file   where to persist the dragged offset (optional)
"""
import os, json, threading, datetime as dt

import objc
from AppKit import (
    NSApplication, NSApp, NSPanel, NSView, NSTextField, NSColor, NSFont, NSMenu,
    NSMenuItem, NSScreen, NSWorkspace, NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel, NSBackingStoreBuffered,
    NSApplicationActivationPolicyAccessory, NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorStationary, NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSScreenSaverWindowLevel, NSTextAlignmentLeft, NSEvent,
)
from Foundation import NSObject, NSTimer, NSMakeRect, NSMakePoint, NSMakeSize

import winbounds

PANEL_H = 30.0
PAD = 12.0            # horizontal padding inside the pill
MARGIN_RIGHT = 14.0   # default gap from the window's right edge
OFFSET_TOP = 5.0      # default gap below the window's top edge
TICK = 0.3            # seconds — position-follow cadence

SHORT = {"session": "5h", "weekly_all": "wk", "weekly_opus": "Opus",
         "weekly_sonnet": "Son", "weekly_cowork": "Cowork"}


def dot(pct, sev="normal"):
    sev = (sev or "normal").lower()
    if sev in ("exceeded", "critical", "blocked") or (pct or 0) >= 95:
        return "🔴"
    if sev in ("warning", "warn") or (pct or 0) >= 80:
        return "🟠"
    if (pct or 0) >= 50:
        return "🟡"
    return "🟢"


def htok(n):
    n = n or 0
    for u, d in (("B", 1e9), ("M", 1e6), ("K", 1e3)):
        if n >= d:
            return f"{n/d:.1f}{u}"
    return str(int(n))


def reset(iso):
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except Exception:
        return ""
    now = dt.datetime.now(t.tzinfo)
    secs = (t - now).total_seconds()
    rel = "now" if secs <= 0 else (f"in {int(secs//60)}m" if secs < 3600 else
          (f"in {int(secs//3600)}h" if secs < 86400 else f"in {int(secs//86400)}d"))
    when = t.strftime("%H:%M") if t.date() == now.date() else t.strftime("%a %H:%M")
    return f"resets {when} ({rel})"


def reset_short(iso):
    """Compact 'resets in' countdown: '24m' / '3h' / '2d'."""
    if not iso:
        return ""
    try:
        t = dt.datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone()
    except Exception:
        return ""
    secs = (t - dt.datetime.now(t.tzinfo)).total_seconds()
    if secs <= 0:
        return "now"
    if secs < 3600:
        return f"{int(secs // 60)}m"
    if secs < 86400:
        return f"{int(round(secs / 3600))}h"
    return f"{int(round(secs / 86400))}d"


def _primary_height():
    for s in NSScreen.screens():
        f = s.frame()
        if f.origin.x == 0 and f.origin.y == 0:
            return f.size.height
    return NSScreen.mainScreen().frame().size.height


class DragView(NSView):
    def initWithController_(self, ctrl):
        self = objc.super(DragView, self).initWithFrame_(NSMakeRect(0, 0, 200, PANEL_H))
        self.ctrl = ctrl
        self.setWantsLayer_(True)
        self.layer().setCornerRadius_(8.0)
        self.layer().setBackgroundColor_(NSColor.colorWithCalibratedWhite_alpha_(0.0, 0.82).CGColor())
        return self

    def hitTest_(self, point):
        # route every click in our area to this view (don't let the label eat it)
        hit = objc.super(DragView, self).hitTest_(point)
        return self if hit is not None else None

    def mouseDown_(self, event):
        # manual drag: record screen mouse + window origin; tick pauses follow
        self.ctrl.dragging = True
        self._m0 = NSEvent.mouseLocation()
        f = self.window().frame()
        self._w0 = (f.origin.x, f.origin.y)

    def mouseDragged_(self, event):
        cur = NSEvent.mouseLocation()
        self.window().setFrameOrigin_(NSMakePoint(
            self._w0[0] + (cur.x - self._m0.x), self._w0[1] + (cur.y - self._m0.y)))

    def mouseUp_(self, event):
        self.ctrl.recomputeOffset()   # lock in the new offset from the window corner
        self.ctrl.dragging = False

    def rightMouseDown_(self, event):
        menu = NSMenu.alloc().init()
        for title, sel in (("Refresh now", "refresh:"), (None, None), ("Quit", "quit:")):
            if title is None:
                menu.addItem_(NSMenuItem.separatorItem())
            else:
                it = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(title, sel, "")
                it.setTarget_(self.ctrl)
                menu.addItem_(it)
        NSMenu.popUpContextMenu_withEvent_forView_(menu, event, self)


class Controller(NSObject):
    def start(self):
        self.latest = None
        self.dirty = False
        self.dragging = False
        self.width = 200.0
        self.lock = threading.Lock()
        self._wake = threading.Event()

        style = NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel
        self.panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(-2000, -2000, self.width, PANEL_H), style, NSBackingStoreBuffered, False)
        self.panel.setLevel_(NSScreenSaverWindowLevel)
        self.panel.setOpaque_(False)
        self.panel.setBackgroundColor_(NSColor.clearColor())
        self.panel.setHasShadow_(True)
        self.panel.setMovable_(True)
        self.panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces |
            NSWindowCollectionBehaviorStationary |
            NSWindowCollectionBehaviorFullScreenAuxiliary)

        self.panel.setContentView_(DragView.alloc().initWithController_(self))

        self.label = NSTextField.alloc().initWithFrame_(NSMakeRect(PAD, 0, 100, PANEL_H))
        self.label.setBezeled_(False); self.label.setDrawsBackground_(False)
        self.label.setEditable_(False); self.label.setSelectable_(False)
        self.label.setTextColor_(NSColor.whiteColor())
        self.label.setFont_(NSFont.systemFontOfSize_(12.0))
        self.label.setAlignment_(NSTextAlignmentLeft)
        self.label.setUsesSingleLineMode_(True)
        self.panel.contentView().addSubview_(self.label)
        self._apply_text(f"{self.cfg['name']} usage…")

        self.off_x, self.off_y = self._load_offset()  # distance from window top-right corner

        threading.Thread(target=self._poll_loop, daemon=True).start()
        NSTimer.scheduledTimerWithTimeInterval_target_selector_userInfo_repeats_(
            TICK, self, "tick:", None, True)
        return self

    def _apply_text(self, line):
        """Set the bar text and auto-size the pill to fit it."""
        self.label.setStringValue_(line)
        self.label.sizeToFit()
        sz = self.label.frame().size
        self.width = sz.width + 2 * PAD
        self.panel.setContentSize_(NSMakeSize(self.width, PANEL_H))
        self.label.setFrame_(NSMakeRect(PAD, (PANEL_H - sz.height) / 2.0, sz.width, sz.height))

    def _poll_loop(self):
        while True:
            try:
                s = self.cfg["fetch"]()
            except Exception as e:
                s = {"plan": {"error": str(e)}, "local": {}, "at": dt.datetime.now().isoformat()}
            with self.lock:
                self.latest = s; self.dirty = True
            self._wake.wait(self.cfg["poll_seconds"]); self._wake.clear()

    def tick_(self, _timer):
        # show the bar only when the app owns the topmost normal window (in front)
        rect = winbounds.active_window_rect(self.cfg["owner"])
        if (rect is not None) != getattr(self, "_last_state", None):
            self._last_state = rect is not None
            print(f"[{self.cfg['name']}] active={rect is not None} rect={rect}", flush=True)
        if rect:
            if not self.dragging:
                x = rect[0] + rect[2] - self.width - self.off_x
                y = _primary_height() - rect[1] - PANEL_H - self.off_y
                self.panel.setFrameOrigin_(NSMakePoint(x, y))
            if not self.panel.isVisible():
                self.panel.orderFront_(None)
        elif self.panel.isVisible() and not self.dragging:
            self.panel.orderOut_(None)

        with self.lock:
            if not self.dirty:
                return
            s = self.latest; self.dirty = False
        line, tip = self.cfg["render"](s)
        self._apply_text(line)
        self.label.setToolTip_(tip)
        self.panel.contentView().setToolTip_(tip)

    def refresh_(self, _):
        self._wake.set()

    def quit_(self, _):
        NSApp.terminate_(None)

    # ---- offset from the window's top-right corner (persisted) ----
    def _offset_path(self):
        return self.cfg.get("offset_file") or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), self.cfg["name"].lower() + "_offset.json")

    def _load_offset(self):
        try:
            with open(self._offset_path()) as f:
                d = json.load(f)
            return float(d["x"]), float(d["y"])
        except Exception:
            return (MARGIN_RIGHT + self.cfg.get("right_extra", 0.0), OFFSET_TOP)

    def _save_offset(self):
        try:
            with open(self._offset_path(), "w") as f:
                json.dump({"x": self.off_x, "y": self.off_y}, f)
        except OSError:
            pass

    def recomputeOffset(self):
        rect = winbounds.active_window_rect(self.cfg["owner"]) or winbounds.window_rect(self.cfg["owner"])
        if not rect:
            return
        f = self.panel.frame()
        self.off_x = (rect[0] + rect[2]) - (f.origin.x + self.width)
        self.off_y = (_primary_height() - rect[1]) - (f.origin.y + PANEL_H)
        self._save_offset()


def run(cfg):
    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)  # no Dock icon
    ctrl = Controller.alloc().init()
    ctrl.cfg = cfg
    ctrl.start()
    app.run()
