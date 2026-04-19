# 🔫 Buckshot Oracle

> "There’s no way it’s red again."  
> — incorrect

A small desktop assistant for Buckshot Roulette that keeps track of the game, estimates probabilities, and learns from your runs over time.

---

## 🧠 What it does

- Estimates odds of red / blue shells using a simple Bayesian model  
- Adjusts its internal weights based on past outcomes  
- Tracks your current round (remaining shells, history, etc.)  
- Logs sessions so you can review what actually happened  

It’s not perfect, but it’s better than guessing.

---

## ⚙️ How it works

At its core, the tool combines:
- current shell distribution (what’s left in the round)  
- learned weights from previous games  
- basic Bayesian updating  

After each reveal, it slightly adjusts its expectations depending on whether the prediction was correct.

Over time, it builds its own bias based on your games.

---

## 🖥️ Features

- Real-time probability display  
- Prediction for the next shell  
- Round history (last shots)  
- Session stats (accuracy, correct / wrong guesses)  
- Item tracking (records which items were useful or not)  
- Inverter support (flips the next prediction)  
- Persistent learning via local JSON storage  

---

## 📂 Data

The assistant stores its state locally:

- shell weights  
- item usage stats  
- round history (last ~100 runs)  

If things get weird, you can always reset everything.

---

## 🚀 Usage

1. Start a new round  
2. Enter the number of red / blue shells  
3. (Optional) add items  
4. Follow predictions and log outcomes as you play  

That’s it.

---

## ⚠️ Disclaimer

This doesn’t “solve” the game.

It just gives you slightly more informed guesses.

Bad decisions are still very much possible.

---

## 🧪 Notes

- The learning system is intentionally lightweight  
- Weights are normalized to avoid drifting too far  
- Predictions can still flip due to randomness or edge cases  

---

## 🤖 Offline Bot

In addition to the desktop Oracle, the repo ships with a self-contained
terminal bot in [`buckshot_bot.py`](./buckshot_bot.py). It simulates the
full Buckshot Roulette game loop (shells, HP, items — handcuffs, hand
saw, magnifying glass, beer, cigarettes, inverter) and lets you play
against a probability-driven AI with no network required.

```bash
python buckshot_bot.py               # play vs the bot
python buckshot_bot.py --watch       # watch the bot play itself
python buckshot_bot.py --sim 1000    # run N bot-vs-bot games
python buckshot_bot.py --seed 42     # deterministic shell order
```

Smoke tests: `python -m pytest tests/`.

---

## 🤝 Contributing

If you want to tweak the model, improve the UI, or add features — go ahead.

---

## ⭐

Star it if it helped.  
Ignore it if you lost anyway.
