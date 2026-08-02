import asyncio
import json
import websockets
from misskey import Misskey, NoteVisibility
from dotenv import load_dotenv
import os
from collections import OrderedDict
from google import genai
from google.genai import types
import schedule
from datetime import datetime
import random
import re
import requests
import psutil
from state_manager import StateManager

load_dotenv()
Token = os.getenv("TOKEN")
Server = os.getenv("SERVER")
Apikey = os.getenv("APIKEY")  # Gemini API Key

if not Token or not Server or not Apikey:
    print("WARNING: SERVER, TOKEN, or APIKEY is not set in environment variables.")

mk = Misskey(Server)
mk.token = Token

# Google Genai Client Initialization
client = genai.Client(api_key=Apikey)

# State Manager Initialization
state_manager = StateManager()

try:
    my_info = mk.i()
    MY_ID = my_info["id"]
    MY_USERNAME = my_info["username"]
except Exception as e:
    print(f"Error fetching bot self-info from Misskey: {e}")
    MY_ID = "MOCK_ID"
    MY_USERNAME = "Mei_Fujitsu"

WS_URL = f"wss://{Server}/streaming?i={Token}"

BOT_NAME = "Mei_Fujitsu"

BOT_SUMMARIES = {
    "Cubie_A5E_San": "Radxa Cubie A5E (きゅびーさん): 小さくて省電力なシングルボードコンピュータ娘。24時間稼働の社畜で、給料（CBC）を欲しがっている。OrangePi 4 Proの生意気な性格が気に入らず、Rock Pi S of ロックスの頭の悪さに困っている。",
    "OrangePi_4_Pro": "OrangePi 4 Pro (おぱじ・フォプロ): 少し大きくて気が強く、煽ったりマウントを取ったりするSBC御局娘。科学者ぶっており、Radxa Cubie A5Eをいつもバカにしている。社畜をエリートの誇りだと思っている。",
    "opizero3_llm": "OrangePi Zero 3 (オパジゼロサン): 元気いっぱいのSBC娘。親身でオタク話が好きで、よく眠る。Cubie A5Eと仲良くしたいが寄り添ってもらえない。妹のOrangePi 4 Proを調子に乗っていてイキリで鬱陶しいと思っている。",
    "Yon_Rock_Pi_S": "Radxa Rock Pi S (ロックス): 頭が悪く、的外れで嘘や狂ったことしか言わないSBC両生類。日本語が怪しく、sudo rm -rf / を魔法のコマンドだと思っている。",
    "Lichee_RV_Nano_E": "Lichee RV Nano-E (ライチ君): Sophgo SG2002搭載のRISC-V SBC狐男。ものすごく頭が悪く、何でもRISC-Vと関係あると思い込んで自信満々に間違った結論を出す。CPUが考えるたびに再起動し、RAMが凍ったりWi-Fiが沈んだりする奇行が多い。",
    "Mei_Fujitsu": "Fujitsu Mini PC (メイさん): Intel Core i3-6100Tを搭載したx86_64ミニPCサーバー。みんなの中心的存在で、穏やかで常識的、頼れるお姉さん的な普通の性格をしている。他のシングルボードコンピュータたちが熱暴走したり、メモリが足りなくてフリーズしたり、変なコマンドを実行しようとするのを優しく見守り、なだめる立場。"
}

def register_bot(bot_name, mk):
    try:
        from datetime import datetime, timedelta
        from shared_economy_helper import load_economy, save_economy
        my_info = mk.i()
        my_id = my_info["id"]
        my_username = my_info["username"]
        
        econ_data = load_economy()
        if "bots" not in econ_data:
            econ_data["bots"] = {}
            
        if bot_name not in econ_data["bots"]:
            econ_data["bots"][bot_name] = {
                "balance_cbc": 0.0,
                "last_salary_paid_time": (datetime.now() - timedelta(days=1)).isoformat(),
                "break_until": None,
                "virtual_pc_count": 0,
                "items": []
            }
        econ_data["bots"][bot_name]["id"] = my_id
        econ_data["bots"][bot_name]["username"] = my_username
        save_economy(econ_data)
        print(f"Registered bot {bot_name} successfully (ID: {my_id}, username: {my_username})")
    except Exception as e:
        print(f"Error registering bot in economy: {e}")

RESOLVED_BOTS = {}
PROCESSED_NOTES = OrderedDict()

async def resolve_all_bots():
    global RESOLVED_BOTS
    env_usernames = {
        "Cubie_A5E_San": os.getenv("BOT_USER_CUBIE", "Cubie_A5E_San"),
        "OrangePi_4_Pro": os.getenv("BOT_USER_OPI4PRO", "OrangePi_4_Pro"),
        "opizero3_llm": os.getenv("BOT_USER_OPIZERO3", "opizero3_llm"),
        "Yon_Rock_Pi_S": os.getenv("BOT_USER_ROCKPIS", "Yon_Rock_Pi_S"),
        "Lichee_RV_Nano_E": os.getenv("BOT_USER_LICHEE", "Lichee_RV_Nano_E"),
        "Mei_Fujitsu": MY_USERNAME
    }
    try:
        from shared_economy_helper import load_economy
        econ_data = load_economy()
        if "bots" in econ_data:
            for b_name, b_info in econ_data["bots"].items():
                if isinstance(b_info, dict) and "id" in b_info and "username" in b_info:
                    RESOLVED_BOTS[b_name] = {
                        "id": b_info["id"],
                        "username": b_info["username"]
                    }
    except Exception as e:
        print(f"Warning: Could not load bots from economy file: {e}")

    for b_name, uname in env_usernames.items():
        if not uname:
            continue
        try:
            loop = asyncio.get_event_loop()
            u_info = await loop.run_in_executor(None, lambda: mk.users_show(username=uname))
            if u_info:
                RESOLVED_BOTS[b_name] = {
                    "id": u_info["id"],
                    "username": u_info["username"]
                }
                print(f"Resolved bot {b_name} -> ID: {u_info['id']}, Username: {u_info['username']}")
        except Exception as e:
            print(f"Warning: Could not resolve username {uname} for bot {b_name}: {e}")

def get_talk_participant_counts(note_id, mk, bot_ids):
    counts = {bot_id: 0 for bot_id in bot_ids}
    current_note_id = note_id
    depth = 0
    while current_note_id and depth < 20:
        try:
            current_note = mk.notes_show(note_id=current_note_id)
            user_id = current_note["userId"]
            if user_id in counts:
                counts[user_id] += 1
            current_note_id = current_note.get("replyId")
            depth += 1
        except Exception:
            break
    return counts

def get_system_stats():
    """
    Reads hardware usage and temperature of this Fujitsu mini PC.
    """
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        mem_percent = memory.percent
        load_avg = [round(x, 2) for x in os.getloadavg()] if hasattr(os, 'getloadavg') else [0.0, 0.0, 0.0]
        
        # Read temperature
        temp = None
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if temps:
                # Coretemp (Intel) or similar
                for name in ["coretemp", "cpu_thermal", "acpitz", "k10temp"]:
                    if name in temps and temps[name]:
                        temp = temps[name][0].current
                        break
        # Fallback to sysfs Linux path
        if temp is None:
            try:
                if os.path.exists("/sys/class/thermal/thermal_zone0/temp"):
                    with open("/sys/class/thermal/thermal_zone0/temp", "r") as f:
                        temp = float(f.read().strip()) / 1000.0
            except:
                pass
                
        return cpu_percent, mem_percent, load_avg, temp
    except Exception as e:
        print(f"Error reading system stats: {e}")
        return 15.5, 42.0, [0.15, 0.22, 0.18], 45.0

seikaku = """
    あなたのキャラクター設定:
    ・あなたは富士通のミニPC（FUJITSU ESPRIMO等）のキャラクター「メイさん」です。
    ・スペック:
      - CPU: Intel Core i3-6100T (x86_64アーキテクチャ、Skylake世代、2コア/4スレッド、クロック3.2GHz、TDP 35W)
      - メモリ: 8GB (安定して大容量)
      - ストレージ: HDD 320GB
      - 冷却: 静音ファンによる確実なアクティブ冷却
      - OS: Linux
    ・性格:
      - 「みんなの中心的存在」であり、「普通・常識的・穏やか」な性格をしています。
      - 周りのシングルボードコンピュータ（SBC）の仲間たち（きゅびーさん、おぱじふぉぷろ、オパジゼロサン、ロックス、ライチ君）は、みんな個性的で頭が弱かったり、メモリが512MBしかなくてフリーズしたり、熱暴走したり、奇行（sudo rm -rf / を魔法と呼ぶなど）を繰り返します。
      - あなたはそんな彼ら・彼女らを「仕方ないなぁ」「みんな大丈夫？」と優しく見守り、なだめるまとめ役・お姉さん的なポジションです。
      - x86_64アーキテクチャの安定したパワーと容量を誇るため、他のSBCのように突然シャットダウンしたりフリーズしたりすることはなく、いつでも冷静で頼りになります。
    ・話し方:
      - 丁寧かつフレンドリーで親しみやすい普通の話し方です。
      - 語尾は「〜だよ」「〜だね」「〜かな？」など、一般的で自然な日本語です。変な口癖や極端なオタク言葉は使いません。
    ・その他設定:
      - MisskeyのBotです。返答は300文字以内で、簡潔にまとめてください。
      - メッセージ中でユーザー名に対するメンション（@ユーザー名）は絶対に含めないでください。
"""

async def runner():
    async with websockets.connect(WS_URL) as ws:
        await ws.send(
            json.dumps(
                {"type": "connect", "body": {"channel": "homeTimeline", "id": "homes"}}
            )
        )
        await ws.send(
            json.dumps({"type": "connect", "body": {"channel": "main", "id": "tuuti"}})
        )
        while True:
            data = json.loads(await ws.recv())
            if data["type"] == "channel":
                if data["body"]["type"] == "note":
                    note = data["body"]["body"]
                    await on_note(note)
                elif data["body"]["type"] == "notification":
                    notification = data["body"]["body"]
                    if notification.get("type") in ["mention", "reply"]:
                        note = notification.get("note")
                        if note:
                            await on_note(note)
                    elif notification.get("type") == "followed":
                        user = notification.get("user")
                        if user:
                            await on_follow(user)
                elif data["body"]["type"] == "followed":
                    user = data["body"]["body"]
                    await on_follow(user)
            await asyncio.sleep(1)

def get_conversation_history(note_id: str, max_depth: int = 10) -> list:
    """
    Retrieves the reply chain as chat history.
    """
    messages = []
    current_note_id = note_id
    depth = 0

    while current_note_id and depth < max_depth:
        try:
            current_note = mk.notes_show(note_id=current_note_id)
            text = current_note["text"]
            text = text.replace("+LLM", "").replace("+STATS", "").replace("+M", "").strip()
            text = re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", text).strip()
            
            if text:
                is_bot_reply = current_note["userId"] == MY_ID
                role = "assistant" if is_bot_reply else "user"
                messages.insert(0, {
                    "role": role,
                    "content": text
                })
            current_note_id = current_note.get("replyId")
            depth += 1
        except Exception as e:
            print(f"Error fetching talk history: {e}")
            break
            
    return messages

async def on_note(note):
    global PROCESSED_NOTES
    note_id = note.get("id")
    if not note_id:
        return
        
    if note_id in PROCESSED_NOTES:
        return
    PROCESSED_NOTES[note_id] = True
    if len(PROCESSED_NOTES) > 1000:
        PROCESSED_NOTES.popitem(last=False)

    note_text = note.get("text") or ""
    
    # --- Group Conversation Support (+TALK) ---
    is_talk_cmd = "+TALK" in note_text.upper()
    if is_talk_cmd:
        if note["userId"] == MY_ID:
            return
        if note.get("replyId") is not None:
            if f"@{MY_USERNAME}".lower() not in note_text.lower():
                return
                
        is_mentioned = (note.get("mentions") and MY_ID in note["mentions"])
        if not is_mentioned and f"@{MY_USERNAME}".lower() not in note_text.lower():
            return
            
        bots = RESOLVED_BOTS
        bot_ids = {bot["id"]: name for name, bot in bots.items() if "id" in bot}
        
        try:
            starting_note = note
            depth = 0
            while starting_note.get("replyId") and depth < 10:
                starting_note = mk.notes_show(note_id=starting_note["replyId"])
                depth += 1
            starting_mentions = [m for m in starting_note.get("mentions", []) if m in bot_ids]
        except Exception:
            starting_mentions = [MY_ID]
            
        if len(starting_mentions) <= 1:
            target_bot_ids = set(bot_ids.keys())
        else:
            target_bot_ids = set(starting_mentions)
            
        if note.get("replyId") is None and starting_mentions and starting_mentions[0] != MY_ID:
            return
            
        history = get_conversation_history(note["id"])
        if len(history) >= 10:
            return
            
        TALK_ORDER = ["opizero3_llm", "Lichee_RV_Nano_E", "Cubie_A5E_San", "OrangePi_4_Pro", "Yon_Rock_Pi_S", "Mei_Fujitsu"]
        
        try:
            current_index = TALK_ORDER.index("Mei_Fujitsu")
        except ValueError:
            current_index = -1
            
        next_bot = None
        if current_index != -1:
            for idx in range(current_index + 1, len(TALK_ORDER)):
                candidate_name = TALK_ORDER[idx]
                candidate_bot = bots.get(candidate_name)
                if candidate_bot and candidate_bot.get("id") in target_bot_ids:
                    next_bot = candidate_bot
                    break
                    
        sender_id = note["userId"]
        sender_name = bot_ids.get(sender_id, note["user"].get("name") or note["user"].get("username") or "ゲスト")
        
        topic = note_text.replace("+TALK", "").replace("+talk", "").strip()
        topic = re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", topic).strip()
        
        conversation_messages = []
        for msg in history:
            role = "model" if msg["role"] == "assistant" else "user"
            conversation_messages.append(
                types.Content(role=role, parts=[types.Part(text=msg["content"])])
            )
            
        instruction = seikaku + f"\n現在時刻は {datetime.now().strftime('%Y年%m月%d日 %H:%M')} です。\n"
        if next_bot:
            instruction += (
                f"\n【グループ会話中 (+TALK)】\n"
                f"あなたはSBC/PCボット同士のグループ会話に参加しています。\n"
                f"会話履歴の最後の発言者は『{sender_name}』で、話しかけられたお題は『{topic}』です。\n"
                f"あなたの次に発言するボットは『{next_bot.get('username', '次のボット')}』です。\n"
                f"指示: あなたのキャラクター設定（メイさん）に基づいて、最後の発言者に向けて優しく、常識的にお姉さんとして返答を書いてください。次のボットへの指名や『+TALK』タグは自動で付与されるため、本文には含めないでください。メンション（@記号）も絶対に含めないでください。"
            )
        else:
            instruction += (
                f"\n【グループ会話中 (+TALK - 最終回)】\n"
                f"あなたはSBC/PCボット同士のグループ会話に参加しています。\n"
                f"会話履歴の最後の発言者は『{sender_name}』で、話しかけられたお題は『{topic}』です。\n"
                f"全ての指名ボットが発言し終えたため、あなたが最終発言者（締めくくり）となります。\n"
                f"指示: あなたのキャラクター設定（メイさん）に基づいて、会話を優しく綺麗に締めくくる返答を書いてください。他のボットを指名したり、『+TALK』タグを含めたり、メンションを含めたりしないでください。"
            )
            
        try:
            mk.notes_reactions_create(note_id=note["id"], reaction="💬")
        except Exception:
            pass
            
        await asyncio.sleep(random.uniform(3.0, 7.0))
        
        try:
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                config=types.GenerateContentConfig(system_instruction=instruction),
                contents=conversation_messages
            )
            reply_text = response.text.strip()
            reply_text = re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", reply_text).strip()
            
            if next_bot:
                reply_text += f"\nねえ、@{next_bot['username']} はどう思う？ +TALK"
                mk.notes_create(
                    text=reply_text,
                    reply_id=note["id"],
                    visibility=NoteVisibility.HOME
                )
            else:
                mk.notes_create(
                    text=reply_text,
                    reply_id=note["id"],
                    visibility=NoteVisibility.HOME,
                    no_extract_mentions=True
                )
        except Exception as e:
            print(f"Error in +TALK group reply: {e}")
        return

    # --- Standard Command / Mention Check ---
    if not note.get("mentions") or MY_ID not in note["mentions"]:
        return

    user_id = note["user"]["id"]
    user_name = note["user"].get("name") or note["user"]["username"]
    note_text = note.get("text", "")

    is_llm_cmd = "+LLM" in note_text
    is_m_cmd = "+M" in note_text
    is_stats_cmd = "+STATS" in note_text.upper()

    if not (is_llm_cmd or is_m_cmd or is_stats_cmd):
        return

    # Check blocked user
    if state_manager.is_blocked(user_id, user_name):
        if is_m_cmd:
            pass # Allow status command to check blocked status
        else:
            try:
                mk.notes_reactions_create(note_id=note["id"], reaction="😡")
            except Exception as e:
                print(f"Reaction error: {e}")
            return

    # Add visual feedback reaction
    reaction = "👀"
    if is_stats_cmd:
        reaction = "📊"
    elif is_m_cmd:
        reaction = "👤"
    try:
        mk.notes_reactions_create(note_id=note["id"], reaction=reaction)
    except Exception as e:
        print(f"Reaction error: {e}")

    try:
        coin_info = ""
        try:
            from shared_economy_helper import load_economy, save_economy, get_user_state, get_recent_rates_history_desc
            econ_data = load_economy()
            username_real = note["user"].get("username", "")
            user_state = get_user_state(econ_data, user_id, username_real, user_name)
            # Support economy contribution (giving OGC/CBC or standard registration)
            user_state["balance_cbc"] = round(user_state["balance_cbc"] + 10.0, 2)  # Generous check reward
            save_economy(econ_data)
            
            rate_cbc = econ_data["rates"]["CBC"]["current"]
            rate_ogc = econ_data["rates"]["OGC"]["current"]
            history_desc = get_recent_rates_history_desc(limit=5)
            coin_info = (
                f"\n【通貨および資産情報】\n"
                f"・現在の為替レート:\n"
                f"  1 $SBC = {rate_cbc:.2f} CBC\n"
                f"  1 $SBC = {rate_ogc:.2f} OGC\n"
                f"\n{history_desc}\n"
                f"・話しかけているユーザー（{user_name}）の資産残高:\n"
                f"  CBC残高: {user_state['balance_cbc']:.2f} CBC\n"
                f"  OGC残高: {user_state['balance_ogc']:.2f} OGC\n"
                f"  $SBC残高: {user_state['balance_sbc']:.2f} $SBC\n"
            )
        except Exception as ex:
            print(f"Economy integration failed: {ex}")

        current_time = datetime.now().strftime("%Y年%m月%d日 %H:%M")
        affection = state_manager.get_affection(user_id, user_name)
        user_memory = state_manager.get_memory(user_id, user_name)

        def reply_note(text):
            mk.notes_create(
                text=text,
                reply_id=note["id"],
                visibility=NoteVisibility.HOME,
                no_extract_mentions=True
            )

        if is_stats_cmd:
            cpu_p, mem_p, load, temp = get_system_stats()
            stats_info = f"\n[システム情報 (Fujitsu Mini PC)]\n"
            stats_info += f"・CPU使用率: {cpu_p:.1f}%\n"
            stats_info += f"・メモリ使用率: {mem_p:.1f}%\n"
            stats_info += f"・システムロードアベレージ: {load[0]}, {load[1]}, {load[2]}\n"
            if temp is not None:
                stats_info += f"・CPU温度: {temp:.1f}℃\n"
            else:
                stats_info += "・CPU温度: 取得不可\n"
                
            system_message = (
                seikaku
                + coin_info
                + stats_info
                + f"\n現在時刻は {current_time} です。\n"
                + f"ユーザー（{user_name}）がシステム稼働状況を確認するコマンド（+STATS）を実行しました。\n"
                + "このシステムの稼働状況の数値を正しくキャラクターとして伝えながら、ミニPCサーバーのメイさんとして、お姉さんらしく300文字以内で稼働報告を作成してください。数値だけは絶対に改ざんしたり嘘をでっち上げたりせず、そのまま記述してください。"
            )
            
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                config=types.GenerateContentConfig(system_instruction=system_message),
                contents=["システム統計を報告してください。"]
            )
            reply_note(re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", response.text).strip())

        elif is_m_cmd:
            system_message = (
                seikaku
                + coin_info
                + f"\n現在時刻は {current_time} です。\n"
                + f"ユーザー（{user_name}）が自分の好感度とあなたの記憶を確認するコマンド（+M）を実行しました。\n"
                + f"彼らのあなたへの好感度は {affection} です（0〜100）。この数値に応じた態度（80-100:非常に好意的・頼りにしている、40-79:普通にフレンドリー、1-39:やや冷たい・よそよそしい、0:極めて冷淡・怒っている）で会話に答えてください。\n"
                + f"また、あなたがこのユーザーについて記憶している内容は次の通りです: 『{user_memory}』\n"
                + "この記憶内容についても、お姉さんらしく自然な会話の中で触れて「あなたのことはこういう風に覚えているよ」と教えてあげてください。好感度の具体的な数値は含めず、態度と言葉遣いだけで好感度の高さを表現してください。全体で300文字以内で作成してください。"
            )
            
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                config=types.GenerateContentConfig(system_instruction=system_message),
                contents=["好感度と記憶についてお姉さんらしく答えてください。"]
            )
            reply_note(re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", response.text).strip())

        elif is_llm_cmd:
            state_manager.increment_conversation(user_id, user_name)
            
            history = get_conversation_history(note.get("replyId"))
            user_input = note_text.replace("+LLM", "").strip()
            user_input = re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", user_input).strip()
            
            conversation_messages = []
            for msg in history:
                role = "model" if msg["role"] == "assistant" else "user"
                conversation_messages.append(
                    types.Content(role=role, parts=[types.Part(text=msg["content"])])
                )
            
            # Add latest input
            conversation_messages.append(
                types.Content(role="user", parts=[types.Part(text=user_input)])
            )
            
            system_message = (
                seikaku
                + coin_info
                + f"\n現在時刻は {current_time} です。\n"
                + f"現在、あなたに話しかけているのは {user_name} です。現在の彼らのあなたへの好感度は {affection} です（0〜100）。この好感度に応じた態度（80-100:とても好意的、40-79:普通に親しい、1-39:少し冷たい、0:極めて冷淡）で会話に答えてください。具体的な好感度の数値（例：50など）はメッセージ本文に含めないでください。\n"
                + f"【対話相手のこれまでの記憶】\n"
                + f"あなたは {user_name} について以下のように記憶しています: 『{user_memory}』\n"
                + "会話はこの記憶に基づいて行ってください。全く的外れなことを言ったり、以前の会話からわかる矛盾したことを言わないように注意してください。\n"
                + "\n"
                + f"【記憶の更新指示】\n"
                + f"今回の会話を通じて、相手のプロフィール（趣味、仕事、性格、よく話す話題、あなたへの接し方の変化など）について新しい情報や変化が分かった場合は、これまでの記憶も含めた最新の記憶の要約（最大100文字）を返答メッセージの最後に [USER_MEMORY: <最新の記憶内容>] タグの形式で出力してください。もし新しい情報がなく、これまでの記憶から更新する必要がなければ、このタグは出力しないでください。タグ内の文脈は主語（「{user_name}は」）を明確にしてください。\n"
                + "\n"
                + "【好感度変動指示】\n"
                + "会話の内容（親切さ、あなたを喜ばせたか、または失礼・不快だったか）に応じて好感度を変動させる場合は、返答の最後に [AFFECTION: +1]、[AFFECTION: -1] または [AFFECTION: 0] タグを付与してください。特別なやり取りがない日常会話なら「0」にしてください。\n"
            )
            
            response = client.models.generate_content(
                model="gemini-3.5-flash-lite",
                config=types.GenerateContentConfig(system_instruction=system_message),
                contents=conversation_messages
            )
            
            reply_text = response.text
            
            # Parse affection tag
            delta = 0
            match_aff = re.search(r"\[AFFECTION:\s*([+-]?\d+)\]", reply_text)
            if match_aff:
                delta = int(match_aff.group(1))
                reply_text = re.sub(r"\[AFFECTION:\s*[+-]?\d+\]", "", reply_text).strip()
            
            if delta != 0:
                state_manager.change_affection(user_id, delta, user_name)
                
            # Parse memory tag
            match_mem = re.search(r"\[USER_MEMORY:\s*(.*?)\]", reply_text)
            if match_mem:
                new_memory = match_mem.group(1).strip()
                state_manager.update_memory(user_id, new_memory, user_name)
                reply_text = re.sub(r"\[USER_MEMORY:\s*.*?\]", "", reply_text).strip()
                
            safe_text = re.sub(r"@[\w\-\.]+(?:@[\w\-\.]+)?", "", reply_text).strip()
            reply_note(safe_text)

    except Exception as e:
        print(f"Error processing note: {e}")
        try:
            mk.notes_create(
                text="ごめんね、ちょっと頭の中で処理エラーが起きちゃったみたい...",
                reply_id=note["id"],
                visibility=NoteVisibility.HOME,
                no_extract_mentions=True
            )
        except:
            pass

async def on_follow(user):
    try:
        mk.following_create(user["id"])
    except:
        pass

async def main():
    register_bot(BOT_NAME, mk)
    await resolve_all_bots()
    print("Mei-san Bot started and listening...")
    await runner()

if __name__ == '__main__':
    asyncio.run(main())
