"""Backfill missing contract types from stored titles and parsed text."""

import argparse

from app.core.db import SessionLocal
from app.core.storage import get_storage
from app.models.contract import ContractFile
from app.models.user import User
from app.services.contract_type_service import ensure_default_contract_types, resolve_contract_type


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--username", default="admin", help="Only backfill this user's contracts")
    parser.add_argument(
        "--include-classified",
        action="store_true",
        help="Reclassify contracts that already have a type",
    )
    args = parser.parse_args()

    storage = get_storage()
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == args.username).first()
        if user is None:
            raise SystemExit(f"User not found: {args.username}")

        ensure_default_contract_types(db)
        query = db.query(ContractFile).filter(ContractFile.user_id == user.id)
        if not args.include_classified:
            query = query.filter(ContractFile.contract_type_id.is_(None))

        updated = 0
        skipped = 0
        for contract in query.order_by(ContractFile.id):
            content = ""
            if contract.content_path:
                try:
                    content = storage.read_text(contract.content_path)
                except Exception as exc:  # noqa: BLE001
                    print(f"WARN id={contract.id} parsed text unavailable: {exc}")
            contract_type = resolve_contract_type(db, contract.title, content)
            if contract_type is None:
                skipped += 1
                continue
            contract.contract_type_id = contract_type.id
            updated += 1
            print(f"UPDATED id={contract.id} type={contract_type.name} title={contract.title}")

        db.commit()
        print(f"DONE username={args.username} updated={updated} skipped={skipped}")


if __name__ == "__main__":
    main()
