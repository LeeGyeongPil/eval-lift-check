from inspect_ai import Task, task
from inspect_ai.dataset import Sample
from inspect_ai.scorer import CORRECT, INCORRECT, Score, accuracy, scorer
from inspect_ai.solver import solver


@solver
def noop():
    async def solve(state, generate):
        return state
    return solve


@scorer(metrics=[accuracy()])
def parity():
    async def score(state, target):
        n = int(str(state.sample_id)[1:])
        ok = (n + state.epoch) % 3 != 0
        return Score(value=CORRECT if ok else INCORRECT, answer="x")
    return score


@task
def tiny():
    return Task(dataset=[Sample(id=f"q{i}", input=f"What is {i}+1?", target=str(i + 1)) for i in range(4)],
                solver=[noop()], scorer=parity())
