"""SQLAlchemy 2.0 Core 테이블 정의. ORM 매핑 없이 Table 객체로 직접 다룬다(01절 "ORM 마법 최소화").

파일이 커져서 08절 데이터모델 그룹 그대로 5개 모듈로 나눴다(CLAUDE.md 500줄 상한).
"""

from app.models.base import metadata
from app.models.auth import auth_session, login_attempt
from app.models.customers import (
    customer,
    customer_followed_org,
    customer_interest,
    customer_interest_term,
    interest_topic,
    saved_search,
)
from app.models.notices import (
    award,
    classification_correction,
    keyword_rule,
    notice,
    notice_score,
    notice_version,
    org,
    raw_payload,
    requirement,
)
from app.models.analysis import (
    analysis,
    analysis_check,
    analysis_doc,
    analysis_flag,
    analysis_requirement,
)
from app.models.catalog import product, product_cert, product_reference, product_spec
from app.models.reports import newsletter_report
from app.models.sources import (
    audit_log,
    source,
    source_config,
    source_credential,
    source_field_map,
    source_run,
)

__all__ = [
    "metadata",
    # auth
    "auth_session",
    "login_attempt",
    # customers
    "customer",
    "interest_topic",
    "customer_interest",
    "customer_interest_term",
    "customer_followed_org",
    "saved_search",
    # notices
    "raw_payload",
    "notice",
    "notice_version",
    "notice_score",
    "requirement",
    "org",
    "award",
    "keyword_rule",
    "classification_correction",
    # analysis
    "analysis",
    "analysis_doc",
    "analysis_requirement",
    "analysis_flag",
    "analysis_check",
    # catalog
    "product",
    "product_spec",
    "product_cert",
    "product_reference",
    # reports
    "newsletter_report",
    # sources
    "source",
    "source_config",
    "source_field_map",
    "source_credential",
    "source_run",
    "audit_log",
]
