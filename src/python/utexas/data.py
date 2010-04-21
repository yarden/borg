"""
utexas/data.py

Storage and retrieval of research data.

@author: Bryan Silverthorn <bcs@cargo-cult.org>
"""

from uuid                       import (
    UUID,
    uuid4,
    )
from sqlalchemy                 import (
    Float,
    Column,
    String,
    Integer,
    Boolean,
    ForeignKey,
    UnicodeText,
    LargeBinary,
    )
from sqlalchemy.orm             import (
    relation,
    sessionmaker,
    )
from sqlalchemy.ext.declarative import declarative_base
from cargo.log                  import get_logger
from cargo.sql.alchemy          import (
    SQL_UUID,
    SQL_JSON,
    SQL_List,
    SQL_Engines,
    UTC_DateTime,
    SQL_TimeDelta,
    )
from cargo.flags                import (
    Flag,
    Flags,
    with_flags_parsed,
    )

log             = get_logger(__name__)
DatumBase       = declarative_base()
ResearchSession = sessionmaker()
module_flags    = \
    Flags(
        "Research Data Storage",
        Flag(
            "--research-database",
            default = "sqlite:///:memory:",
            metavar = "DATABASE",
            help    = "use research DATABASE by default [%default]",
            ),
        )

class TaskRecord(DatumBase):
    """
    One task.
    """

    __tablename__ = "tasks"

    uuid = Column(SQL_UUID, primary_key = True)
    type = Column(String)

    __mapper_args__ = {"polymorphic_on": type}

class SAT_TaskRecord(TaskRecord):
    """
    One satisfiability task in DIMACS CNF format.
    """

    __tablename__   = "sat_tasks"
    __mapper_args__ = {"polymorphic_identity": "cnf_sat"}

    uuid = Column(SQL_UUID, ForeignKey(TaskRecord.uuid), primary_key = True)
    hash = Column(LargeBinary(length = 64))

    TASK_NAMESPACE = UUID("8e67a81a-717c-4206-8831-6007bc8f111f")

class TaskNameRecord(DatumBase):
    """
    Place a task in the context of a collection.
    """

    __tablename__ = "task_descriptions"

    uuid       = Column(SQL_UUID, primary_key = True, default = uuid4)
    task_uuid  = Column(SQL_UUID, ForeignKey("tasks.uuid"), nullable = False)
    name       = Column(String)
    collection = Column(String)

    task = relation(TaskRecord)

class SAT_SolverRecord(DatumBase):
    """
    Some solver for some domain.
    """

    __tablename__ = "sat_solvers"

    name = Column(String, primary_key = True)
    type = Column(String)

class SAT_PreprocessorRecord(DatumBase):
    """
    Some solver for some domain.
    """

    __tablename__ = "sat_preprocessors"

    name = Column(String, primary_key = True)

class SAT_PreprocessorRunRecord(DatumBase):
    """
    Information about one run of a preprocessor on a SAT task.
    """

    __tablename__ = "sat_preprocessor_runs"

    uuid                  = Column(SQL_UUID, primary_key = True, default = uuid4)
    preprocessor_name     = Column(String, ForeignKey("sat_preprocessors.name"), nullable = False)
    preprocessor_run_uuid = Column(SQL_UUID, ForeignKey("sat_preprocessor_runs.uuid"))
    started               = Column(UTC_DateTime)
    usage_elapsed         = Column(SQL_TimeDelta)
    proc_elapsed          = Column(SQL_TimeDelta)
    cutoff                = Column(SQL_TimeDelta)
    fqdn                  = Column(String)
    stdout                = Column(UnicodeText)
    stderr                = Column(UnicodeText)
    exit_status           = Column(Integer)
    exit_signal           = Column(Integer)

    preprocessor = relation(SAT_PreprocessorRecord)

class SAT_SolverRunRecord(DatumBase):
    """
    Information about one run of a solver on a SAT task.
    """

    __tablename__ = "sat_solver_runs"

    uuid                  = Column(SQL_UUID, primary_key = True, default = uuid4)
    task_uuid             = Column(SQL_UUID, ForeignKey("sat_tasks.uuid"), nullable = False)
    preprocessor_run_uuid = Column(SQL_UUID, ForeignKey("sat_preprocessor_runs.uuid"))
    solver_name           = Column(String, ForeignKey("sat_solvers.name"), nullable = False)
    started               = Column(UTC_DateTime)
    usage_elapsed         = Column(SQL_TimeDelta)
    proc_elapsed          = Column(SQL_TimeDelta)
    cutoff                = Column(SQL_TimeDelta)
    fqdn                  = Column(String)
    seed                  = Column(Integer)
    stdout                = Column(UnicodeText)
    stderr                = Column(UnicodeText)
    exit_status           = Column(Integer)
    exit_signal           = Column(Integer)
    satisfiable           = Column(Boolean)
    certificate           = Column(SQL_List(Integer))

    task             = relation(SAT_TaskRecord)
    solver           = relation(SAT_SolverRecord)
    preprocessor_run = relation(SAT_PreprocessorRunRecord)

class PortfolioScoreWorldRecord(DatumBase):
    """
    World from a (set of) portfolio tests.
    """

    __tablename__ = "portfolio_score_worlds"

    uuid     = Column(SQL_UUID, primary_key = True, default = uuid4)
    ntrain   = Column(Integer)
    ntest    = Column(Integer)
    limit    = Column(SQL_TimeDelta)
    prefix   = Column(String)
    discount = Column(Float)
    tags     = Column(SQL_List(String))

class PortfolioScoreRecord(DatumBase):
    """
    Result of a portfolio test.
    """

    __tablename__ = "portfolio_scores"

    # columns
    uuid         = Column(SQL_UUID, primary_key = True, default = uuid4)
    world_uuid   = Column(SQL_UUID, ForeignKey("portfolio_score_worlds.uuid"))
    model_name   = Column(String)
    planner_name = Column(String)
    components   = Column(Integer)
    solved       = Column(Integer)
    spent        = Column(SQL_TimeDelta)
    utility      = Column(Float)
    tags         = Column(SQL_List(String))

    # relations
    world = relation(PortfolioScoreWorldRecord)

def research_connect(engines = SQL_Engines.default, flags = module_flags.given):
    """
    Connect to research data storage.
    """

    flags = module_flags.merged(flags)

    return engines.get(flags.research_database)
