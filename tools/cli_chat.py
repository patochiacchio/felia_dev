import argparse
import requests

BASE = "http://127.0.0.1:8000"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--session", default="demo")
    args = parser.parse_args()

    print("Felia CLI — escribí y Enter (salir con :q)")
    while True:
        msg = input("> ").strip()
        if msg == ":q":
            break

        # Enviamos con claves estándar (la API también acepta session_id/message)
        payload = {"session": args.session, "text": msg}
        r = requests.post(f"{BASE}/chat", json=payload, timeout=60)
        try:
            data = r.json()
        except Exception:
            print(f"[HTTP {r.status_code}] {r.text}")
            continue

        if "reply" in data:
            print(data["reply"])
        else:
            print(data)

    print("Chau!")

if __name__ == "__main__":
    main()
