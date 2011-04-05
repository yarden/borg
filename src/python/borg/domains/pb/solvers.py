"""@author: Bryan Silverthorn <bcs@cargo-cult.org>"""

import os
import re
import tempfile
import itertools
import numpy
import cargo
import borg

logger = cargo.get_logger(__name__, default_level = "INFO")

nlc_commands = {
    "pbct-0.1.2-linear": ["{root}/pbct-0.1.2-linux32", "--model", "{task}"],
    "sat4j-pb-v20101225": [
        "java",
        "-server",
        "-jar",
        "{root}/sat4j-pb-v20101225/sat4j-pb.jar",
        "{task}",
        ],
    "sat4j-pb-v20101225-cutting": [
        "java",
        "-server",
        "-jar",
        "{root}/sat4j-pb-v20101225/sat4j-pb.jar",
        "CuttingPlanes",
        "{task}",
        ],
    }
lin_commands = {
    "bsolo_pb10-l1": ["{root}/bsolo_pb10", "-t1000000", "-m2048", "-l1", "{task}"],
    "bsolo_pb10-l2": ["{root}/bsolo_pb10", "-t1000000", "-m2048", "-l2", "{task}"],
    "bsolo_pb10-l3": ["{root}/bsolo_pb10", "-t1000000", "-m2048", "-l3", "{task}"],
    "wbo1.4a": ["{root}/wbo1.4a", "-time-limit=1000000", "-file-format=opb", "{task}"],
    "wbo1.4b-fixed": ["{root}/wbo1.4b-fixed", "-time-limit=1000000", "-file-format=opb", "{task}"],
    "clasp-1.3.7": ["{root}/clasp-1.3.7/clasp-1.3.7-x86-linux", "--seed={seed}", "{task}"],
    }
scip_commands = {
    "scip-2.0.1-clp": ["{root}/scip-2.0.1.linux.x86_64.gnu.opt.clp", "-f", "{task}"],
    "scip-2.0.1-spx": ["{root}/scip-2.0.1.linux.x86_64.gnu.opt.spx", "-f", "{task}"],
    }

def parse_competition(stdout):
    """Parse output from a standard competition solver."""

    match = re.search(r"^s +([a-zA-Z ]+) *\r?$", stdout, re.M)

    if match:
        (answer_type,) = match.groups()
        answer_type = answer_type.strip().upper()

        if answer_type in ("SATISFIABLE", "OPTIMUM FOUND"):
            certificate = []

            for line in re.findall(r"^v ([ x\-0-9]*) *\r?$", stdout, re.M):
                certificate.extend(line.split())

            if len(certificate) == 0:
                return None
        elif answer_type == "UNSATISFIABLE":
            certificate = None
        else:
            return None

        return (answer_type, certificate)

    return None

class PseudoBooleanSolverFactory(object):
    def __init__(self, command):
        self._command = command

    def __call__(self, task, stm_queue = None, solver_id = None):
        return \
            borg.solver_io.RunningSolver(
                parse_competition,
                self._command,
                task.path,
                stm_queue = stm_queue,
                solver_id = solver_id,
                )

class LinearPseudoBooleanSolverFactory(PseudoBooleanSolverFactory):
    def __call__(self, task, stm_queue = None, solver_id = None):
        return \
            borg.solver_io.RunningSolver(
                parse_competition,
                self._command,
                task.get_linearized_path(),
                stm_queue = stm_queue,
                solver_id = solver_id,
                )

def parse_scip(variables, optimization, stdout):
    """Parse output from the SCIP solver(s)."""

    answer_match = re.search(r"^SCIP Status *: *problem is solved \[([a-zA-Z ]+)\] *\r?$", stdout, re.M)

    if answer_match:
        (status,) = answer_match.groups()

        if status == "optimal solution found":
            answer_type = "OPTIMUM FOUND" if optimization else "SATISFIABLE"
            trues = map(int, re.findall(r"^x([0-9]+) *1[ \t]*\(obj:.+\) *\r?$", stdout, re.M))
            solution = numpy.zeros(variables, bool)

            for v in trues:
                solution[v - 1] = True

            certificate = [("" if t else "-") + ("x%i" % (v + 1)) for (v, t) in enumerate(solution)]
        elif status == "infeasible":
            answer_type = "UNSATISFIABLE"
            certificate = None
        else:
            return None

        return (answer_type, certificate)

    return None

class SCIP_SolverFactory(object):
    def __init__(self, command):
        self._command = command

    def __call__(self, task, stm_queue = None, solver_id = None):
        parse = cargo.curry(parse_scip, task.opb.N, task.opb.objective is not None)

        return \
            borg.solver_io.RunningSolver(
                parse,
                self._command,
                task.path,
                stm_queue = stm_queue,
                solver_id = solver_id,
                )

def parse_opbdp(variables, optimization, stdout):
    """Parse output from the SCIP solver(s)."""

    if re.search(r"^Constraint Set is unsatisfiable\r?$", stdout, re.M):
        return ("UNSATISFIABLE", None)
    elif re.search(r"^Global Minimum: ****** -?[0-9]+ ******\r?$", stdout, re.M):
        solution_match = re.search(r"^0-1 Variables fixed to 1 :([x0-9 ]*)\r?$", stdout, re.M)

        if solution_match:
            solution = numpy.zeros(variables, bool)
            (solution_chunk,) = answer_match.groups()

            for part in solution_chunk.split():
                solution[int(part[1:]) - 1] = True

            return (
                "OPTIMUM FOUND" if optimization else "SATISFIABLE",
                [("" if t else "-") + ("x%i" % (v + 1)) for (v, t) in enumerate(solution)],
                )

    return None

class OPBDP_SolverFactory(object):
    def __call__(self, task, stm_queue = None, solver_id = None):
        parse = cargo.curry(parse_opbdp, task.opb.N, task.opb.objective is not None)
        nl_flag = ["-n"] if task.nonlinear else []

        return \
            borg.solver_io.RunningSolver(
                parse,
                ["{root}/opbdp-1.1.3/opbdp", "-s", "-v1"] + nl_flag + ["{task}"],
                task.path,
                stm_queue = stm_queue,
                solver_id = solver_id,
                )

def write_minion_from_pb(instance, minion_file):
    minion_file.write("MINION 3\n")
    minion_file.write("**VARIABLES**\n")
    minion_file.write("BOOL b[{0}]\n".format(instance.N))

    if instance.objective is not None:
        minion_file.write("BOUND c {{{0}..{1}}}\n".format(-2**30, 2**30))

    minion_file.write("**CONSTRAINTS**\n")

    if instance.objective is not None:
        weights = ",".join(str(w) for (w, _) in instance.objective)
        variables = ",".join("b[{0}]".format(v) for (_, v) in instance.objective)

        minion_file.write("weightedsumgeq([{0}],[{1}],c)\n".format(weights, variables))
        minion_file.write("weightedsumleq([{0}],[{1}],c)\n".format(weights, variables))

    for i in xrange(instance.M):
        j = instance.constraints.indptr[i]
        k = instance.constraints.indptr[i + 1]
        total = instance.totals[i]
        weights = ",".join(map(str, instance.constraints.data[j:k]))
        variables = ",".join(map("b[{0}]".format, instance.constraints.indices[j:k]))

        minion_file.write("weightedsumgeq([{0}],[{1}],{2})\n".format(weights, variables, total))

        if instance.relations[i] == 1:
            minion_file.write("weightedsumleq([{0}],[{1}],{2})\n".format(weights, variables, total))

    minion_file.write("**SEARCH**\n")

    if instance.objective is not None:
        minion_file.write("MINIMIZING c\n")

    minion_file.write("PRINT [b]\n")
    minion_file.write("**EOF**\n")

def parse_minion(instance, stdout):
    answer_match = re.search(r"^Problem solvable\?: ([a-z]+)\r?$", stdout, re.M)

    if answer_match:
        (status,) = answer_match.groups()

        if status == "yes":
            answer_type = "SATISFIABLE" if instance.objective is None else "OPTIMUM FOUND"
            solution_group = re.findall(r"^Sol: ([01 ]+)\r?$", stdout, re.M)[-1]
            solution = map(int, solution_group.split())
            certificate = [("" if t == 1 else "-") + ("x%i" % (v + 1)) for (v, t) in enumerate(solution)]
        elif status == "no":
            answer_type = "UNSATISFIABLE"
            certificate = None
        else:
            return None

        return (answer_type, certificate)

    return None

def build_minion_pb_solver(task, stm_queue = None, solver_id = None):
    input_path = task.support_paths.get("minion")

    if input_path is None:
        (fd, input_path) = tempfile.mkstemp(suffix = ".minion")

        task.support_paths["minion"] = input_path

        with os.fdopen(fd, "w") as input_file:
            write_minion_from_pb(task.opb, input_file)

        logger.info("wrote minion input file to %s", input_path)

    return \
        borg.solver_io.RunningSolver(
            cargo.curry(parse_minion, task.opb),
            ["{root}/minion-0.12/bin/minion", "-noresume", "{task}"],
            input_path,
            stm_queue = stm_queue,
            solver_id = solver_id,
            )

nlc_named = dict(zip(nlc_commands, map(PseudoBooleanSolverFactory, nlc_commands.values())))
lin_named = dict(zip(lin_commands, map(LinearPseudoBooleanSolverFactory, lin_commands.values())))
scip_named = dict(zip(scip_commands, map(SCIP_SolverFactory, scip_commands.values())))
minion_named = {"minion-0.12": build_minion_pb_solver}
named = dict(nlc_named.items() + lin_named.items() + scip_named.items() + minion_named.items())

