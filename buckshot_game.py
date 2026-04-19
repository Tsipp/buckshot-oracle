"""Tkinter GUI for the offline Buckshot Roulette bot.

Gives the terminal bot in ``buckshot_bot.py`` a visual front-end:

* HP dots for both players
* Live / blank shell counters with a pictogram row
* Item buttons you can click to use
* Shoot-self / shoot-opponent buttons
* A scrolling action log
* Two modes: ``Play vs Bot`` and ``Watch Bot vs Bot``

Run with::

    python buckshot_game.py

No external dependencies — only the Python standard library.
"""

from __future__ import annotations

import random
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox
from typing import Optional

import buckshot_bot as core


# ---------------------------------------------------------------------------
# Theme — matches the existing Oracle palette so the two apps feel related.
# ---------------------------------------------------------------------------


class Theme:
    BG_PRIMARY = "#0a0a0f"
    BG_SECONDARY = "#12121a"
    BG_CARD = "#16161f"
    BG_TERTIARY = "#1a1a25"
    RED = "#ff2d55"
    BLUE = "#00b4ff"
    GOLD = "#ffd60a"
    GREEN = "#30d158"
    ORANGE = "#ff9f0a"
    PURPLE = "#bf5af2"
    TEXT = "#ffffff"
    TEXT_DIM = "#8e8e93"
    BORDER = "#2c2c2e"


# Icons / short labels for each item — short so they fit buttons cleanly.
ITEM_META = {
    "handcuffs": ("🔗", "Cuffs", "Skip opponent's next turn"),
    "hand_saw":  ("🪚", "Saw",   "Next shot deals 2 damage"),
    "magnifying_glass": ("🔍", "Peek", "Check the current shell"),
    "beer":      ("🍺", "Beer",  "Eject and reveal the current shell"),
    "cigarettes": ("🚬", "Cigs", "Heal 1 HP (up to max)"),
    "inverter":  ("🔄", "Invert", "Flip the current shell live↔blank"),
}


# ---------------------------------------------------------------------------
# GUI
# ---------------------------------------------------------------------------


class BuckshotGUI:
    """Main window. Owns one ``core.GameState`` at a time."""

    BOT_DELAY_MS = 900  # pause between bot actions so you can read them

    def __init__(self, root: tk.Tk, *, seed: Optional[int] = None) -> None:
        self.root = root
        self.root.title("Buckshot Roulette — Offline")
        self.root.configure(bg=Theme.BG_PRIMARY)
        self.root.geometry("900x720")
        self.rng = random.Random(seed)

        self.state: Optional[core.GameState] = None
        self.human_idx: Optional[int] = 0  # None in watch mode
        self.busy = False  # blocks input while the bot is thinking / animating

        self._build_fonts()
        self._build_layout()
        self._show_mode_selector()

    # ------------------------------------------------------------------ ui

    def _build_fonts(self) -> None:
        self.f_title = tkfont.Font(family="Helvetica", size=22, weight="bold")
        self.f_header = tkfont.Font(family="Helvetica", size=14, weight="bold")
        self.f_body = tkfont.Font(family="Helvetica", size=11)
        self.f_small = tkfont.Font(family="Helvetica", size=10)
        self.f_mono = tkfont.Font(family="Courier", size=10)

    def _build_layout(self) -> None:
        header = tk.Frame(self.root, bg=Theme.BG_PRIMARY)
        header.pack(fill="x", pady=(12, 6))
        tk.Label(
            header,
            text="⚡  BUCKSHOT ROULETTE  ⚡",
            bg=Theme.BG_PRIMARY,
            fg=Theme.GOLD,
            font=self.f_title,
        ).pack()
        tk.Label(
            header,
            text="Offline — You vs the Dealer-Bot",
            bg=Theme.BG_PRIMARY,
            fg=Theme.TEXT_DIM,
            font=self.f_small,
        ).pack()

        # Opponent panel, centre (shells), player panel, controls, log.
        self.opp_panel = self._make_player_panel("Dealer-Bot", Theme.RED)
        self.opp_panel["frame"].pack(fill="x", padx=16, pady=(10, 6))

        self.center = tk.Frame(self.root, bg=Theme.BG_SECONDARY, bd=1, relief="flat")
        self.center.pack(fill="x", padx=16, pady=6)
        self._build_center(self.center)

        self.you_panel = self._make_player_panel("You", Theme.BLUE)
        self.you_panel["frame"].pack(fill="x", padx=16, pady=6)

        self.controls = tk.Frame(self.root, bg=Theme.BG_PRIMARY)
        self.controls.pack(fill="x", padx=16, pady=(8, 4))
        self._build_controls(self.controls)

        self.log_frame = tk.Frame(self.root, bg=Theme.BG_CARD)
        self.log_frame.pack(fill="both", expand=True, padx=16, pady=(6, 12))
        self._build_log(self.log_frame)

    def _make_player_panel(self, default_name: str, accent: str) -> dict:
        frame = tk.Frame(self.root, bg=Theme.BG_CARD, bd=0)

        top = tk.Frame(frame, bg=Theme.BG_CARD)
        top.pack(fill="x", padx=12, pady=(10, 4))

        name_label = tk.Label(
            top,
            text=default_name,
            bg=Theme.BG_CARD,
            fg=accent,
            font=self.f_header,
        )
        name_label.pack(side="left")

        hp_canvas = tk.Canvas(
            top, width=180, height=24, bg=Theme.BG_CARD, highlightthickness=0
        )
        hp_canvas.pack(side="right")

        items_frame = tk.Frame(frame, bg=Theme.BG_CARD)
        items_frame.pack(fill="x", padx=12, pady=(0, 10))

        return {
            "frame": frame,
            "name": name_label,
            "hp_canvas": hp_canvas,
            "items_frame": items_frame,
            "accent": accent,
        }

    def _build_center(self, parent: tk.Frame) -> None:
        parent.configure(padx=16, pady=14)
        self.shell_canvas = tk.Canvas(
            parent, height=60, bg=Theme.BG_SECONDARY, highlightthickness=0
        )
        self.shell_canvas.pack(fill="x")
        self.shell_info = tk.Label(
            parent,
            text="",
            bg=Theme.BG_SECONDARY,
            fg=Theme.TEXT,
            font=self.f_body,
        )
        self.shell_info.pack(pady=(6, 0))
        self.peek_label = tk.Label(
            parent,
            text="",
            bg=Theme.BG_SECONDARY,
            fg=Theme.GOLD,
            font=self.f_small,
        )
        self.peek_label.pack()

    def _build_controls(self, parent: tk.Frame) -> None:
        self.btn_self = self._mk_button(
            parent, "🔫 Shoot SELF", Theme.BLUE, lambda: self._human_shoot("self")
        )
        self.btn_self.pack(side="left", padx=(0, 8))

        self.btn_opp = self._mk_button(
            parent, "🔫 Shoot DEALER", Theme.RED, lambda: self._human_shoot("opponent")
        )
        self.btn_opp.pack(side="left", padx=(0, 8))

        self.items_bar = tk.Frame(parent, bg=Theme.BG_PRIMARY)
        self.items_bar.pack(side="left", padx=(8, 0))

        self.btn_restart = self._mk_button(
            parent, "↺  New Game", Theme.TEXT_DIM, self._show_mode_selector
        )
        self.btn_restart.pack(side="right")

    def _mk_button(self, parent: tk.Frame, text: str, color: str, cmd) -> tk.Button:
        return tk.Button(
            parent,
            text=text,
            command=cmd,
            bg=Theme.BG_TERTIARY,
            fg=color,
            activebackground=Theme.BG_CARD,
            activeforeground=color,
            font=self.f_body,
            bd=0,
            relief="flat",
            padx=12,
            pady=8,
            cursor="hand2",
        )

    def _build_log(self, parent: tk.Frame) -> None:
        tk.Label(
            parent,
            text="ACTION LOG",
            bg=Theme.BG_CARD,
            fg=Theme.TEXT_DIM,
            font=self.f_small,
        ).pack(anchor="w", padx=10, pady=(8, 2))

        text_frame = tk.Frame(parent, bg=Theme.BG_CARD)
        text_frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.log_text = tk.Text(
            text_frame,
            height=8,
            bg=Theme.BG_TERTIARY,
            fg=Theme.TEXT,
            font=self.f_mono,
            bd=0,
            relief="flat",
            wrap="word",
            state="disabled",
        )
        self.log_text.pack(side="left", fill="both", expand=True)
        scroll = tk.Scrollbar(text_frame, command=self.log_text.yview)
        scroll.pack(side="right", fill="y")
        self.log_text.configure(yscrollcommand=scroll.set)

    # ---------------------------------------------------------------- mode

    def _show_mode_selector(self) -> None:
        dlg = tk.Toplevel(self.root)
        dlg.title("Choose mode")
        dlg.configure(bg=Theme.BG_PRIMARY)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.geometry("360x220")

        tk.Label(
            dlg, text="How do you want to play?",
            bg=Theme.BG_PRIMARY, fg=Theme.TEXT, font=self.f_header,
        ).pack(pady=(20, 14))

        def start(mode: str) -> None:
            dlg.destroy()
            if mode == "play":
                self._start_game(human_idx=0)
            else:
                self._start_game(human_idx=None)

        tk.Button(
            dlg, text="🎮  Play vs Bot", command=lambda: start("play"),
            bg=Theme.BG_TERTIARY, fg=Theme.BLUE, font=self.f_body,
            bd=0, padx=16, pady=10, cursor="hand2",
        ).pack(fill="x", padx=40, pady=6)

        tk.Button(
            dlg, text="👁   Watch Bot vs Bot", command=lambda: start("watch"),
            bg=Theme.BG_TERTIARY, fg=Theme.GOLD, font=self.f_body,
            bd=0, padx=16, pady=10, cursor="hand2",
        ).pack(fill="x", padx=40, pady=6)

        tk.Button(
            dlg, text="Quit", command=self.root.destroy,
            bg=Theme.BG_TERTIARY, fg=Theme.TEXT_DIM, font=self.f_small,
            bd=0, padx=10, pady=6, cursor="hand2",
        ).pack(pady=(14, 0))

    # --------------------------------------------------------- game setup

    def _start_game(self, *, human_idx: Optional[int]) -> None:
        self.human_idx = human_idx
        # Panel layout is fixed: opp_panel (top) renders players[1];
        # you_panel (bottom) renders players[0]. Name assignment must match.
        if human_idx is None:
            self.opp_panel["name"].config(text="Bot-A", fg=Theme.RED)
            self.you_panel["name"].config(text="Bot-B", fg=Theme.BLUE)
            p1_bot, p2_bot = True, True
            p1_name, p2_name = "Bot-B", "Bot-A"
        else:
            self.opp_panel["name"].config(text="Dealer-Bot", fg=Theme.RED)
            self.you_panel["name"].config(text="You", fg=Theme.BLUE)
            p1_bot, p2_bot = False, True
            p1_name, p2_name = "You", "Dealer-Bot"

        # In this GUI, panel order is: opponent = index 1, you = index 0.
        self.state = core.start_round(
            p1_name=p1_name,
            p2_name=p2_name,
            hp=core.DEFAULT_MAX_HP,
            rng=self.rng,
            p1_is_bot=p1_bot,
            p2_is_bot=p2_bot,
        )
        self._clear_log()
        self._log(
            f"New round — {self.state.live_left()} live / "
            f"{self.state.blank_left()} blank shells loaded."
        )
        self._refresh()
        self._after_action()

    # ------------------------------------------------------------- render

    def _refresh(self) -> None:
        if self.state is None:
            return
        you = self.state.players[0]
        opp = self.state.players[1]

        self._draw_hp(self.you_panel, you)
        self._draw_hp(self.opp_panel, opp)
        self._draw_items(self.you_panel, you, clickable=(self.human_idx == 0))
        self._draw_items(self.opp_panel, opp, clickable=False)
        self._draw_shells()

        your_turn = (
            self.human_idx is not None
            and self.state.current == self.human_idx
            and not self.busy
            and all(p.alive() for p in self.state.players)
        )
        self._set_controls_enabled(your_turn)

    def _draw_hp(self, panel: dict, player: core.Player) -> None:
        canvas = panel["hp_canvas"]
        canvas.delete("all")
        r, gap = 9, 6
        x = 0
        for i in range(player.max_hp):
            color = Theme.GREEN if i < player.hp else Theme.BORDER
            canvas.create_oval(x, 4, x + r * 2, 4 + r * 2, fill=color, outline=color)
            x += r * 2 + gap
        canvas.create_text(
            x + 10, 4 + r,
            text=f"{player.hp}/{player.max_hp} HP",
            fill=Theme.TEXT, font=self.f_small, anchor="w",
        )

    def _draw_items(self, panel: dict, player: core.Player, *, clickable: bool) -> None:
        frame = panel["items_frame"]
        for w in frame.winfo_children():
            w.destroy()
        if not player.items:
            tk.Label(
                frame, text="(no items)",
                bg=Theme.BG_CARD, fg=Theme.TEXT_DIM, font=self.f_small,
            ).pack(side="left")
            return

        for idx, item in enumerate(player.items):
            icon, short, tip = ITEM_META.get(item, ("?", item, item))
            btn_text = f"{icon}  {short}"
            btn = tk.Button(
                frame,
                text=btn_text,
                bg=Theme.BG_TERTIARY,
                fg=Theme.TEXT,
                activebackground=Theme.BG_CARD,
                font=self.f_small,
                bd=0, relief="flat", padx=8, pady=4,
                cursor="hand2" if clickable else "arrow",
                state="normal" if clickable else "disabled",
                disabledforeground=Theme.TEXT_DIM,
            )
            if clickable:
                btn.config(command=lambda it=item: self._human_use_item(it))
            btn.pack(side="left", padx=(0, 6))
            self._attach_tooltip(btn, tip)

    def _draw_shells(self) -> None:
        assert self.state is not None
        canvas = self.shell_canvas
        canvas.delete("all")
        canvas.update_idletasks()
        w = max(canvas.winfo_width(), 600)
        n = self.state.shells_left()
        if n == 0:
            canvas.create_text(
                w / 2, 30, text="(reloading...)",
                fill=Theme.TEXT_DIM, font=self.f_body,
            )
            self.shell_info.config(text="")
            self.peek_label.config(text="")
            return

        slot = 42
        pad = 8
        total_width = n * slot + (n - 1) * pad
        x0 = max(12, (w - total_width) // 2)
        y0 = 14
        for i in range(n):
            # The first shell is the "next" one — known shells (peek / bot's
            # own memory during play-vs-bot) get colored; others are neutral.
            known_color = None
            if i == 0 and 0 in self.state.known_to_bot and self.human_idx is None:
                # In watch mode we don't actually know what either bot saw;
                # don't leak that to the human viewer.
                known_color = None
            elif i == 0 and self._human_knows_current():
                known_color = Theme.RED if self.state.shells[0] else Theme.BLUE

            fill = known_color or Theme.BORDER
            outline = Theme.GOLD if i == 0 else Theme.BORDER
            canvas.create_rectangle(
                x0, y0, x0 + slot, y0 + 36, fill=fill, outline=outline, width=2,
            )
            x0 += slot + pad

        live, blank = self.state.live_left(), self.state.blank_left()
        info = f"Shells: {n}    🔴 live {live}    🔵 blank {blank}"
        if self.state.saw_active:
            info += "    🪚 saw loaded (next shot = 2 dmg)"
        if 1 in self.state.handcuffed:
            info += "    🔗 dealer is cuffed"
        if 0 in self.state.handcuffed:
            info += "    🔗 you are cuffed"
        self.shell_info.config(text=info)

        if self._human_knows_current():
            label = "LIVE" if self.state.shells[0] else "BLANK"
            self.peek_label.config(text=f"Next shell: {label}")
        else:
            self.peek_label.config(text="")

    # ----------------------------------------------------------- state ui

    def _human_knows_current(self) -> bool:
        """Track whether the human has legitimately peeked/ejected/inverted."""
        return getattr(self, "_human_peeked", False)

    def _set_controls_enabled(self, enabled: bool) -> None:
        st = "normal" if enabled else "disabled"
        for btn in (self.btn_self, self.btn_opp):
            btn.config(state=st)

    # ---------------------------------------------------------- log utils

    def _log(self, msg: str) -> None:
        self.log_text.config(state="normal")
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")
        self.log_text.config(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.config(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.config(state="disabled")

    # -------------------------------------------------------- tooltip

    def _attach_tooltip(self, widget: tk.Widget, text: str) -> None:
        tip = {"win": None}

        def show(_e):
            if tip["win"] is not None:
                return
            x = widget.winfo_rootx() + 10
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            w = tk.Toplevel(widget)
            w.wm_overrideredirect(True)
            w.wm_geometry(f"+{x}+{y}")
            tk.Label(
                w, text=text, bg=Theme.BG_CARD, fg=Theme.TEXT,
                font=self.f_small, bd=1, relief="solid", padx=6, pady=3,
            ).pack()
            tip["win"] = w

        def hide(_e):
            if tip["win"] is not None:
                tip["win"].destroy()
                tip["win"] = None

        widget.bind("<Enter>", show)
        widget.bind("<Leave>", hide)

    # --------------------------------------------------------- human input

    def _human_shoot(self, target: str) -> None:
        if self.state is None or self.busy:
            return
        if self.state.current != self.human_idx:
            return
        self.busy = True
        # Human's peek flag is consumed on any fire (the shell changes).
        self._human_peeked = False
        core.resolve_shot(self.state, self.state.current, target, self._log)
        self._refresh()
        self.root.after(self.BOT_DELAY_MS, self._after_action)

    def _human_use_item(self, item: str) -> None:
        if self.state is None or self.busy:
            return
        if self.state.current != self.human_idx:
            return
        self.busy = True
        prev_shell = self.state.peek_current()
        core.apply_item(self.state, self.state.current, item, self._log)
        # Reveal info to the human for peek / beer / inverter.
        if item == "magnifying_glass":
            self._human_peeked = True
        elif item == "inverter" and prev_shell is not None:
            # Inverter flips; if we knew the value before, we know it still.
            self._human_peeked = True
        elif item == "beer":
            # Beer consumes the shell; the log already revealed it.
            self._human_peeked = False
        self._refresh()
        self.root.after(400, self._after_item_used)

    def _after_item_used(self) -> None:
        """After a human uses an item, keep control (no turn change)."""
        self.busy = False
        self._refresh()
        if not self._check_game_end():
            # Still human's turn — if they used all items, they still need
            # to shoot. Nothing else to schedule.
            pass

    # --------------------------------------------------------- driver loop

    def _after_action(self) -> None:
        """Called shortly after a shot; advances the bot turns if needed."""
        self.busy = False
        if self._check_game_end():
            return
        if self.state is None:
            return

        # Reload chamber if empty.
        if self.state.shells_left() == 0:
            self.state.shells = core.new_loadout(self.state.rng)
            self.state.known_to_bot.clear()
            self.state.saw_active = False
            self.state.handcuffed.clear()
            self._human_peeked = False
            core.deal_items(self.state, self.state.rng, count=2)
            self._log(
                f"[Reload] {self.state.live_left()} live / "
                f"{self.state.blank_left()} blank shells loaded."
            )

        self._refresh()

        # If it's a bot's turn (either in play-vs-bot or watch mode), schedule
        # the next bot action so the UI has time to breathe between moves.
        current = self.state.current
        human_turn = (self.human_idx is not None and current == self.human_idx)
        if not human_turn:
            self.busy = True
            self.root.after(self.BOT_DELAY_MS, self._bot_step)

    def _bot_step(self) -> None:
        if self.state is None:
            return
        me = self.state.current
        action, arg = core._bot_choose_action(self.state, me)
        who = self.state.players[me].name
        self._log(f"→ {who}: {action} {arg or ''}".rstrip())

        if action == "use_item":
            assert arg is not None
            core.apply_item(self.state, me, arg, self._log)
            self._refresh()
            # Bot keeps the turn after using an item.
            self.root.after(self.BOT_DELAY_MS, self._bot_step)
            return

        if action == "shoot":
            assert arg in ("self", "opponent")
            core.resolve_shot(self.state, me, arg, self._log)
            self._refresh()
            self.root.after(self.BOT_DELAY_MS, self._after_action)
            return

        # Unknown action: skip.
        self.state.advance_turn()
        self.root.after(self.BOT_DELAY_MS, self._after_action)

    def _check_game_end(self) -> bool:
        if self.state is None:
            return False
        dead = [p for p in self.state.players if not p.alive()]
        if not dead:
            return False
        winner = next(p for p in self.state.players if p.alive())
        self._log(f"\n*** {winner.name} wins! ***")
        self._set_controls_enabled(False)
        # Show a little dialog once.
        self.root.after(
            300,
            lambda: messagebox.showinfo(
                "Round over",
                f"{winner.name} wins the round.",
            ),
        )
        return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> int:
    root = tk.Tk()
    BuckshotGUI(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
