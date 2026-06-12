import yaml, json
from app.main import app


def gen_json():
    with open("docs/api-spec.json", "w") as f:
        json.dump(app.openapi(), f, indent=2)

def gen_yaml():
    with open("docs/api-spec.json") as f:
        spec = json.load(f)
    with open("docs/api-spec.yml", "w") as f:
        yaml.dump(spec, f, sort_keys=False)

if __name__ == "__main__":
    gen_json()
    gen_yaml()    

