# EK Telegram Manager — Member Select + Add Attempt

## Termux
```bash
pkg update -y
pkg install python -y
pip install -r requirements.txt
python ek.py
```

## Use
1. Get `api_id` and `api_hash` from https://my.telegram.org → API development tools.
2. Run script and sign in with your own Telegram account.
3. Menu 1: fetch the Target group's visible member list.
4. Menu 2: choose member numbers, e.g. `1,3,5`.
5. Menu 4: enter the Destination group and type `YES` only if every selected person has agreed to join.
6. Results are saved locally to `~/ek_add_results.json`.

## Important
- Telegram may not return every member and may reject direct adds.
- The script never sends DMs and stops if Telegram rate-limits or restricts the account.
- Direct adds should be attempted only for people who explicitly consented.
- Do not share login codes, 2FA password, API hash, or `.session` file; never upload them to GitHub.
