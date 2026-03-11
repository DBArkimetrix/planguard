from pathlib import Path
import yaml

def main():
    path = Path("docs/safety/regression_risk_score.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    factors = data.get("risk_scoring", {}).get("factors", {})
    total = sum(int(v) for v in factors.values())
    data["risk_scoring"]["total_score"] = total
    threshold = 6
    data["risk_scoring"]["status"] = "pass" if total <= threshold else "blocked"
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    print(f"Computed total score: {total}")
    print(f"Status: {data['risk_scoring']['status']}")

if __name__ == "__main__":
    main()

