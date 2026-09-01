import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.config import get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models import Customer, Dispute, Evidence, Outcome, Transaction  # noqa: F401


@pytest.fixture(scope="session")
def engine():
    """Run tests against a dedicated `<db>_test` database, never the dev/demo
    database -- create_all/drop_all here must not be able to touch the
    dataset loaded by scripts/load_database.py.
    """
    settings = get_settings()
    test_db_name = f"{settings.postgres_db}_test"

    admin_url = settings.database_url.rsplit("/", 1)[0] + "/postgres"
    admin_engine = create_engine(admin_url, future=True, isolation_level="AUTOCOMMIT")
    with admin_engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": test_db_name}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{test_db_name}"'))
    admin_engine.dispose()

    test_url = settings.database_url.rsplit("/", 1)[0] + f"/{test_db_name}"
    engine = create_engine(test_url, future=True)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    session = Session()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db_session):
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Phase 2 (ML) fixtures
#
# Dataset and model artifacts are reproducible rather than committed, so these
# fixtures skip cleanly when a checkout has not yet run the generator or
# scripts/train_model.py.
# ---------------------------------------------------------------------------


def _ml_available() -> bool:
    try:
        import lightgbm  # noqa: F401
        import shap  # noqa: F401
        import sklearn  # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture(scope="session")
def train_split():
    if not _ml_available():
        pytest.skip("ML dependencies not installed")
    from app.ml.data import load_split

    try:
        return load_split("train")
    except FileNotFoundError as exc:
        pytest.skip(f"training data not generated: {exc}")


@pytest.fixture(scope="session")
def train_features(train_split):
    from app.ml.features import build_features

    return build_features(
        train_split.disputes, train_split.transactions, train_split.customers, train_split.evidence
    )


@pytest.fixture(scope="session")
def train_target(train_split, train_features):
    from app.ml.features import extract_target

    return extract_target(train_split.outcomes, train_features.index)


@pytest.fixture(scope="session")
def risk_model():
    if not _ml_available():
        pytest.skip("ML dependencies not installed")
    from app.ml.model import ModelNotAvailableError, load_model

    try:
        return load_model()
    except ModelNotAvailableError as exc:
        pytest.skip(f"model artifacts not present: {exc}")
