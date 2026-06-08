"""
Transform users CSV: hash passwords before COPY to PostgreSQL.
Input:  data/fsm_users_plain.csv   (user_id, email, user_name, plain_password, user_role, photo_path, created_at)
Output: data/fsm_users.csv  (user_id, email, user_name, passwd, user_role, photo_path, created_at)

Use:

python3.12 get_hash.py \
    "$DATA_DIR/fsm_users_plain.csv" \
    "$DATA_DIR/fsm_users.csv"
"""
from datetime import datetime
import csv, bcrypt, sys
from pathlib import Path

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt(rounds=12)).decode()

def transform(input_path: Path, output_path: Path):
    with open(input_path) as fin, open(output_path, "w", newline="") as fout:
        reader = csv.DictReader(fin)
        writer = csv.DictWriter(fout, fieldnames=["user_id", "email", "user_name", "passwd", "user_role", "photo_path", "created_at"])
        writer.writeheader()
        for row in reader:
            writer.writerow({
                "user_id":         row["user_id"],
                "email":           row["email"],
                "user_name":       row["user_name"],
                "passwd":          hash_password(row["plain_password"]),
                "user_role":       row["user_role"],
                "photo_path":      row["photo_path"],
                "created_at":      datetime.now()
            })
    print(f"Hashed {input_path} → {output_path}")

if __name__ == "__main__":
    transform(Path(sys.argv[1]), Path(sys.argv[2]))