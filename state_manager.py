import json
import os
from datetime import datetime, date
import requests

class StateManager:
    def __init__(self, data_path=None):
        env_path = os.getenv("MEI_STATE_PATH")
        if env_path:
            self.data_path = env_path
        elif data_path is None:
            # Place state.json in the same directory as this file
            dir_path = os.path.dirname(os.path.abspath(__file__))
            self.data_path = os.path.join(dir_path, "state.json")
        else:
            self.data_path = data_path
            
        self.data = {
            "user_data": {}
        }
        self.load()

    def load(self):
        if self.data_path.startswith(("http://", "https://")):
            try:
                res = requests.get(self.data_path, headers={"Content-Type": "application/json"}, timeout=5)
                if res.status_code == 200:
                    loaded = res.json()
                    if isinstance(loaded, dict):
                        if "user_data" in loaded:
                            self.data["user_data"].update(loaded["user_data"])
            except Exception as e:
                print(f"Error loading remote state: {e}")
        else:
            if os.path.exists(self.data_path):
                try:
                    with open(self.data_path, "r", encoding="utf-8") as f:
                        loaded = json.load(f)
                        if isinstance(loaded, dict) and "user_data" in loaded:
                            self.data["user_data"].update(loaded["user_data"])
                except Exception as e:
                    print(f"Error loading state: {e}")

    def save(self):
        if self.data_path.startswith(("http://", "https://")):
            try:
                res = requests.put(self.data_path, json=self.data, headers={"Content-Type": "application/json"}, timeout=5)
                if res.status_code not in (200, 201, 204):
                    print(f"Failed to save remote state: {res.status_code}")
            except Exception as e:
                print(f"Error saving remote state: {e}")
        else:
            try:
                with open(self.data_path, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"Error saving state: {e}")

    def _get_user_entry(self, user_id: str, name: str = None) -> dict:
        user_id = str(user_id)
        if user_id not in self.data["user_data"]:
            self.data["user_data"][user_id] = {
                "affection": 50,
                "name": name,
                "memory": "特になし",
                "conversation_count": 0,
                "last_seen": None
            }
        else:
            # Update name if provided
            if name:
                self.data["user_data"][user_id]["name"] = name
                
        return self.data["user_data"][user_id]

    def get_affection(self, user_id: str, name: str = None) -> int:
        entry = self._get_user_entry(user_id, name)
        return entry.get("affection", 50)

    def change_affection(self, user_id: str, delta: int, name: str = None) -> int:
        entry = self._get_user_entry(user_id, name)
        old_affection = entry.get("affection", 50)
        new_affection = old_affection + delta
        new_affection = max(0, min(100, new_affection))
        
        entry["affection"] = new_affection
        self.save()
        return new_affection

    def get_memory(self, user_id: str, name: str = None) -> str:
        entry = self._get_user_entry(user_id, name)
        return entry.get("memory", "特になし")

    def update_memory(self, user_id: str, memory_text: str, name: str = None):
        entry = self._get_user_entry(user_id, name)
        entry["memory"] = memory_text
        self.save()

    def increment_conversation(self, user_id: str, name: str = None):
        entry = self._get_user_entry(user_id, name)
        entry["conversation_count"] = entry.get("conversation_count", 0) + 1
        entry["last_seen"] = datetime.now().isoformat()
        self.save()

    def is_blocked(self, user_id: str, name: str = None) -> bool:
        # Checks if affection is currently 0
        return self.get_affection(user_id, name) == 0
