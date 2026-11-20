# Документація EquiReduce

**EquiReduce** — незалежна Python-бібліотека для точної редукції
систем рівнянь у SymPy та формальної перевірки еквівалентності в Lean 4.

Доступна версія розробки `0.1.0.dev0`: алгебраїчна редукція, координатні
карти, обмежений пошук, напівявні й неявні ДАЕ з доказами траєкторій. Поточні перевірки й
незавершені задачі наведено у [звіті виконання](progress.md).
Для використання почніть із [практичної інструкції](quickstart.md).

Рекомендований порядок читання: призначення → математичний контракт →
алгоритми → API → Lean → тестування → план реалізації. Для роботи з
похідними додатково обов'язковий розділ про DAE.

```{toctree}
:maxdepth: 2
:caption: Специфікація та розробка

overview
quickstart
progress
mathematical_contract
algebraic_reduction
coordinates
dae
implicit_dae
dnipro
architecture
api
reference
examples
lean
artifacts
testing
development
roadmap
implementation_plan
decisions
glossary
```
