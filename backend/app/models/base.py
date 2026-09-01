from sqlalchemy import MetaData

# 모든 Table이 공유하는 메타데이터. Alembic autogenerate의 target_metadata로도 쓰인다.
metadata = MetaData()
