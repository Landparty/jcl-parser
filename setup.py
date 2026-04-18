from setuptools import setup

try:
    from mypyc.build import mypycify

    USE_MYPYC = True
except ImportError:
    USE_MYPYC = False

modules = [
    "jclparser/__init__.py",
    "jclparser/condition_parser.py",
    "jclparser/continuation_handler.py",
    "jclparser/dataset_lifecycle.py",
    "jclparser/errors.py",
    "jclparser/explosion.py",
    "jclparser/include_loader.py",
    "jclparser/jcl_file_type.py",
    "jclparser/jes_statements.py",
    "jclparser/lint/__init__.py",
    "jclparser/lint/base.py",
    "jclparser/lint/config.py",
    "jclparser/lint/rules.py",
    "jclparser/lint/runner.py",
    "jclparser/metrics.py",
    "jclparser/model.py",
    "jclparser/parameter_ast.py",
    "jclparser/parameter_validators.py",
    "jclparser/parser.py",
    "jclparser/plugins/__init__.py",
    "jclparser/plugins/base.py",
    "jclparser/proc_loader.py",
    "jclparser/program_profiles/__init__.py",
    "jclparser/program_profiles/base.py",
    "jclparser/program_profiles/idcams.py",
    "jclparser/program_profiles/iebgener.py",
    "jclparser/program_profiles/iefbr14.py",
    "jclparser/program_profiles/ikjeft01.py",
    "jclparser/program_profiles/registry.py",
    "jclparser/program_profiles/sort.py",
    "jclparser/rc_analysis.py",
    "jclparser/sql_detector.py",
    "jclparser/system_symbols.py",
    "jclparser/utils.py",
    "jclparser/validators.py",
]

setup(
    ext_modules=mypycify(modules) if USE_MYPYC else [],
)
