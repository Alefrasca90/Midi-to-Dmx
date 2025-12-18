import json
import os

def save_studio_data(data, filename="studio_data.json"):
    try:
        with open(filename, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Errore salvataggio: {e}")

def load_studio_data(filename="studio_data.json"):
    if not os.path.exists(filename): return {}
    try:
        with open(filename, "r") as f:
            return json.load(f)
    except Exception as e:
        print(f"Errore caricamento: {e}")
        return {}