#!/usr/bin/env python3
"""EK Telegram Manager: member viewer + consent-aware add attempt.

This tool can list visible members and manually select entries. It can attempt a direct
add only for members who have explicitly agreed to join and only when Telegram allows it.
It never sends unsolicited DMs and never retries around Telegram limits.
"""
import asyncio
import getpass
import json
from pathlib import Path

from telethon import TelegramClient
from telethon.errors import (
    ApiIdInvalidError, PhoneCodeInvalidError, PasswordHashInvalidError,
    FloodWaitError, ChatAdminRequiredError, ChannelPrivateError,
    UserNotParticipantError, UserPrivacyRestrictedError,
    UserNotMutualContactError, UserChannelsTooMuchError,
    ChatWriteForbiddenError, PeerFloodError, RPCError
)
from telethon.tl.types import User

HOME = Path.home()
CONFIG_PATH = HOME / ".ek_tg_manager.json"
SESSION_PATH = str(HOME / ".ek_tg_manager_session")
MEMBERS_PATH = HOME / "ek_target_members.json"
SELECTED_PATH = HOME / "ek_selected_members.json"
RESULTS_PATH = HOME / "ek_add_results.json"

def load_config():
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    try: CONFIG_PATH.chmod(0o600)
    except OSError: pass

def ask_positive_int(prompt):
    while True:
        try:
            value = int(input(prompt).strip())
            if value > 0: return value
        except ValueError: pass
        print("সঠিক ধনাত্মক সংখ্যা দাও।")

def configure():
    print("\nmy.telegram.org → API development tools থেকে API ID ও API Hash নাও।")
    print("কোড, পাসওয়ার্ড, API Hash বা Session ফাইল কাউকে দেবে না।")
    api_id = ask_positive_int("API ID: ")
    api_hash = getpass.getpass("API Hash: ").strip()
    if not api_hash:
        print("API Hash খালি রাখা যাবে না।")
        return None
    cfg = {"api_id": api_id, "api_hash": api_hash}
    save_config(cfg)
    return cfg

async def connect(cfg):
    client = TelegramClient(SESSION_PATH, cfg["api_id"], cfg["api_hash"])
    await client.start(
        phone=lambda: input("ফোন নম্বর (দেশের কোডসহ, যেমন +880...): ").strip(),
        code_callback=lambda: getpass.getpass("Telegram login code: "),
        password=lambda: getpass.getpass("Two-Step Verification password (চালু থাকলে): ")
    )
    return client

async def fetch_members(client, target):
    entity = await client.get_entity(target)
    members = []
    print("\nসদস্যদের তালিকা আনা হচ্ছে; Telegram যতটুকু অনুমতি দেয় ততটুকুই পাওয়া যাবে।")
    async for p in client.iter_participants(entity):
        if not isinstance(p, User):
            continue
        name = " ".join(x for x in [p.first_name, p.last_name] if x) or "(নাম নেই)"
        members.append({"id": p.id, "name": name, "username": p.username or "", "bot": bool(p.bot)})
        i = len(members)
        print(f"{i:>4}. {name} | @{p.username}" if p.username else f"{i:>4}. {name} | username নেই")
    MEMBERS_PATH.write_text(json.dumps(members, ensure_ascii=False, indent=2), encoding="utf-8")
    try: MEMBERS_PATH.chmod(0o600)
    except OSError: pass
    print(f"\nমোট {len(members)} জনের তথ্য পাওয়া গেছে। সেভ: {MEMBERS_PATH}")
    return members

def load_json(path):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except Exception: return []

def select_members():
    members = load_json(MEMBERS_PATH)
    if not members:
        print("আগে Target গ্রুপের তালিকা আনো।")
        return
    print("কমা দিয়ে তালিকার নম্বর দাও (যেমন 1,3,5)।")
    raw = input("নম্বর: ").strip()
    try:
        indexes = sorted({int(v.strip()) for v in raw.split(",") if v.strip()})
        selected = [members[i-1] for i in indexes if 1 <= i <= len(members)]
    except ValueError:
        print("নম্বর সঠিক নয়।")
        return
    SELECTED_PATH.write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding="utf-8")
    try: SELECTED_PATH.chmod(0o600)
    except OSError: pass
    print(f"{len(selected)} জন নির্বাচন করা হয়েছে।")

async def create_invite(client, dest):
    entity = await client.get_entity(dest)
    # Creates a join-request link; does not message anyone.
    invite = await client(functions.messages.ExportChatInviteRequest(
        peer=entity, request_needed=True, title="EK voluntary join"
    ))
    return invite.link

async def add_selected(client):
    selected = load_json(SELECTED_PATH)
    if not selected:
        print("আগে সদস্য নির্বাচন করো।")
        return
    destination = input("Destination গ্রুপের username/link: ").strip()
    if not destination:
        print("Destination খালি রাখা যাবে না।")
        return
    print("\nশুধু যারা স্পষ্টভাবে যোগ দিতে সম্মতি দিয়েছেন, তাদেরই সরাসরি অ্যাড করার চেষ্টা করো।")
    print("Telegram-এর নিয়মে ব্যর্থ হলে আর চেষ্টা/রিট্রাই করা হবে না; কাউকে DM-ও করা হবে না।")
    consent = input("নির্বাচিত প্রত্যেক সদস্যের যোগদানের সম্মতি আছে? (YES লিখো): ").strip()
    if consent != "YES":
        print("বন্ধ করা হয়েছে। সম্মতি ছাড়া অ্যাড করা হবে না।")
        return

    from telethon.tl import functions
    dest_entity = await client.get_entity(destination)
    results = []
    for item in selected:
        result = {"id": item["id"], "name": item["name"], "username": item.get("username", ""), "status": ""}
        try:
            user = await client.get_input_entity(item["id"])
            await client(functions.channels.InviteToChannelRequest(channel=dest_entity, users=[user]))
            result["status"] = "success"
            print(f"✅ অ্যাড হয়েছে: {item['name']}")
        except (UserPrivacyRestrictedError, UserNotMutualContactError, UserChannelsTooMuchError) as e:
            result["status"] = "not_allowed"
            result["detail"] = type(e).__name__
            print(f"⏭️ অ্যাড করা যায়নি: {item['name']} — Telegram অনুমতি দেয়নি")
        except FloodWaitError as e:
            result["status"] = "stopped_rate_limit"
            result["detail"] = f"FloodWait {e.seconds}s"
            results.append(result)
            print(f"⛔ Telegram rate limit দিয়েছে ({e.seconds}s)। নিরাপত্তার জন্য কাজ বন্ধ।")
            break
        except (PeerFloodError, ChatWriteForbiddenError) as e:
            result["status"] = "stopped_restriction"
            result["detail"] = type(e).__name__
            results.append(result)
            print("⛔ Telegram সীমাবদ্ধতা দিয়েছে। আর চেষ্টা করা হবে না; কাজ বন্ধ।")
            break
        except RPCError as e:
            result["status"] = "failed"
            result["detail"] = str(e)
            print(f"❌ ব্যর্থ: {item['name']} — {type(e).__name__}")
        except Exception as e:
            result["status"] = "failed"
            result["detail"] = type(e).__name__
            print(f"❌ ব্যর্থ: {item['name']} — {type(e).__name__}")
        results.append(result)

    RESULTS_PATH.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    try: RESULTS_PATH.chmod(0o600)
    except OSError: pass
    success = sum(r["status"] == "success" for r in results)
    print(f"\nরিপোর্ট: সফল {success} | প্রক্রিয়াকৃত {len(results)} | রিপোর্ট ফাইল: {RESULTS_PATH}")
    print("বাকি সদস্যদের জন্য প্রয়োজন হলে স্বেচ্ছায় Join Request-সহ invite link তৈরি করো।")

async def main():
    cfg = load_config()
    if not cfg.get("api_id") or not cfg.get("api_hash"):
        cfg = configure()
        if not cfg: return
    try:
        client = await connect(cfg)
    except Exception as e:
        print(f"লগইন সমস্যা: {e}")
        return
    try:
        me = await client.get_me()
        print(f"\nলগইন: {me.first_name or ''} (@{me.username or 'username নেই'})")
        while True:
            print("\n=== EK Telegram Manager ===")
            print("1. Target Group-এর সদস্য তালিকা")
            print("2. তালিকা থেকে সদস্য নির্বাচন")
            print("3. নির্বাচিত সদস্যদের তালিকা")
            print("4. সম্মত সদস্যদের অ্যাড করার চেষ্টা")
            print("0. বের হও")
            choice = input("অপশন: ").strip()
            if choice == "1":
                target = input("Target group username/link: ").strip()
                try: await fetch_members(client, target)
                except FloodWaitError as e: print(f"Telegram অপেক্ষা করতে বলেছে: {e.seconds} সেকেন্ড। পরে চেষ্টা করো।")
                except (ChatAdminRequiredError, ChannelPrivateError, UserNotParticipantError) as e: print(f"অ্যাক্সেস/অনুমতির সমস্যা: {e}")
                except Exception as e: print(f"তালিকা আনা যায়নি: {e}")
            elif choice == "2":
                select_members()
            elif choice == "3":
                selected = load_json(SELECTED_PATH)
                if not selected: print("কেউ নির্বাচন করা হয়নি।")
                for i, p in enumerate(selected, 1):
                    u = f"@{p['username']}" if p.get("username") else "username নেই"
                    print(f"{i}. {p['name']} | {u} | ID: {p['id']}")
                print(f"মোট: {len(selected)}")
            elif choice == "4":
                await add_selected(client)
            elif choice == "0":
                break
            else: print("সঠিক অপশন দাও।")
    except KeyboardInterrupt:
        print("\nবন্ধ করা হয়েছে।")
    finally:
        await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
