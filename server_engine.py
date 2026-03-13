import json
import random
import os

class ServerEngine:
    DB_PATH = "servers.json"

    @classmethod
    def load_servers(cls):
        if not os.path.exists(cls.DB_PATH):
            return []
        try:
            with open(cls.DB_PATH, "r") as f:
                return json.load(f)
        except Exception:
            return []

    @classmethod
    def save_servers(cls, servers):
        with open(cls.DB_PATH, "w") as f:
            json.dump(servers, f, indent=2)

    @classmethod
    def get_random_server(cls):
        servers = cls.load_servers()
        if not servers:
            return os.getenv("DEFAULT_LINK")
        return random.choice(servers)

    @classmethod
    def add_server(cls, url):
        servers = cls.load_servers()
        if url not in servers:
            servers.append(url)
            cls.save_servers(servers)
            return True
        return False

    @classmethod
    def clear_servers(cls):
        cls.save_servers([])
        return True

if __name__ == "__main__":
    print(f"Random Server: {ServerEngine.get_random_server()}")
