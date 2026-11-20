# Початок роботи

Інструкція для реалізованої алгебраїчної версії `0.1.0.dev0`.
Координатний пошук і експериментальні ДАЕ описані в окремих розділах.
Команди виконуються з кореня `EquiReduce`.

## Встановлення

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,docs]'
```

Для використання лише ядра достатньо `pip install -e .`.
Потрібен Python 3.11+ і SymPy 1.14; Lean не потрібний для імпорту.

## Скорочення у SymPy

```python
import sympy as sp
from equireduce import System, reduce_system, verify_certificate

x, y, a = sp.symbols("x y a", real=True)
system = System.algebraic(
    (a*y - x, y + x - 1), (x, y),
    parameters=(a,), conditions=(sp.Ne(a, 0),),
)
result = reduce_system(system, candidates=(y,))
assert result.reconstruction[y] == x/a
assert result.remaining_unknowns == (x,)
assert result.coverage == "complete"
assert verify_certificate(system, result.certificate).status.value == "verified"
print(result.reduced_system.residuals)
```

Залишається рівняння, еквівалентне `x/a + x - 1 = 0`.
Без початкової умови `a != 0` результат буде `coverage="conditional"`,
а умова з'явиться в `additional_conditions`.
Знакові припущення підтримуються. Похідні, дискретні області й рядки
замість SymPy-виразів явно відхиляються.

## Перевірка Lean

Початкове встановлення Elan/Lean виконується окремо. Для закріпленого
Lake-проєкту:

```bash
cd lean
MATHLIB_NO_CACHE_ON_UPDATE=1 lake update
lake exe cache get Mathlib.Basic.Real.Basic Mathlib.Tactic.FieldSimp Mathlib.Tactic.LinearCombination Mathlib.Tactic.Linarith Mathlib.Tactic.NormNum Mathlib.Tactic.Ring Mathlib.Analysis.Calculus.Deriv.Pow Mathlib.Analysis.Calculus.Deriv.Inv Mathlib.Analysis.Calculus.Deriv.Add Mathlib.Tactic.Convert
cd ..
```

Після підготовки залежностей:

```python
from equireduce import LeanConfig, reduce_system

verified = reduce_system(
    system, candidates=(y,), proof="require",
    lean=LeanConfig(project_dir="lean"),
)
assert verified.formal_check.status.value == "verified"
print(verified.formal_check.axioms)
```

`proof="generate"` лише створює джерело. `proof="require"` повертає
результат тільки після компіляції та перевірки аксіом.
Формальний піднабір зараз: раціональна арифметика, цілі степені,
предикати умов і нерозкриті функції. Наприклад, явний `sin` у залишку
дає `unsupported`, а не удаваний доказ.

## Переносний комплект

```python
from equireduce import export_artifact, load_artifact

export_artifact(verified, "examples/output/my-proof")
restored = load_artifact("examples/output/my-proof")
assert restored.reconstruction == verified.reconstruction
assert restored.formal_check.origin == "recorded"
```

Для нової компіляції використайте `verify_with_lean` із завантаженими
`source` та `certificate`. Завантаження JSON саме не запускає Lean.
Щоб записати лише JSON, передайте шлях із суфіксом `.json`.

## Приймальні приклади

```bash
.venv/bin/python examples/flow_balance.py
.venv/bin/python examples/kinematic.py
.venv/bin/python -m examples.run_formal flow_balance
.venv/bin/python -m examples.run_formal kinematic
.venv/bin/python -m examples.run_formal bjt14
.venv/bin/python -m examples.run_formal bjt43
.venv/bin/python -m examples.run_formal bjt143
.venv/bin/python -m examples.dae_first_order
.venv/bin/python -m examples.coordinate_benchmark
```

Формальні приклади створюють перевірені комплекти в `examples/output/`.
`bjt14` приймає всі 14 початкових рівнянь і відновлює 10 виключених
змінних; старий Lean-файл із Dnipro як доказ не використовується.
`bjt143` додатково задає залежність функцій від різниць напруг і
доводить повний перехід від 14 вихідних рівнянь до трьох координат.

## Перевірки

```bash
.venv/bin/python -m pytest -m 'not lean'
EQUIREDUCE_REQUIRE_LEAN=1 .venv/bin/python -m pytest -m lean
.venv/bin/python -m ruff check src tests examples
.venv/bin/python -m mypy src/equireduce
.venv/bin/python -m sphinx -n -W --keep-going -b html docs docs/_build/html
```

Без підготовленого Lean відповідні тести локально пропускаються.
З `EQUIREDUCE_REQUIRE_LEAN=1` це стає помилкою. Тести з підміною процесу
не використовуються як докази математичної коректності.
