# Адаптер Dnipro

## Часовий ДАЕ-конвеєр

`dnipro.analysis.from_time_system` приймає часову `ResidualSystem`,
необов'язкове ручне розбиття на `differential` / `algebraic` та відкритий інтервал.
`assume_real=True` явно реалізує дійсну область для старих позначень
Dnipro. Надаються незмінний знімок джерела з метаданими, карта
позначень та походження рядків.

`adapter.analyze()` викликає структурний аналіз EquiReduce,
`adapter.reduce()` — неявне алгебраїчне виключення. Похідні зберігаються.
`adapter.restore_expression` та `restore_reconstruction` повертають
початкові позначення Dnipro. Контракт і межі символьної перевірки
описані в [неявному API](implicit_dae.md).

З кореня Dnipro:

```bash
python -m examples.dae_pipeline rc
python -m examples.dae_pipeline rl
python -m examples.dae_pipeline rlc
python -m examples.dae_pipeline rc --auto --initial-zero --proof require
python -m examples.dae_pipeline rl --chart-time --proof require
python -m examples.dae_inputs --proof require
```

Ці приклади не інтегрують систему й не шукають числової робочої точки.

`adapter.reduce(auto=True, preferred_differential=(...), max_candidates=32)`
виконує бюджетний пошук. Якщо розбиття опущено при побудові адаптера,
початково всі змінні залишаються збереженими. Ручне розбиття, якщо
задане, повинно містити обидві частини.

Параметри `initial_time`, `initial_values`, `initial_rates`,
`parameter_values` приймають початкові позначення Dnipro й точно
переносяться через `symbol_map`. `initial_check` відрізняє символьні
зобов'язання від доведеної сумісності в точці, без гарантії існування розв'язку.

`adapter.coordinate_transform(variables=..., matrix=..., offset=...)`
створює часову карту. `adapter.reduce_in_coordinates(chart,
differential=..., algebraic=...)` повертає реконструкцію початкових
станів через нові координати. Умова невиродженості діє на всьому
інтервалі; похідні матриці та зсуву враховуються.

Для часової ДАЕ `inputs=(u, ...)` явно оголошує зовнішні дійсні
диференційовні функції. Їхні зразки передаються через
`initial_input_values={u: ...}` і
`initial_input_rates={Derivative(u, t): ...}` в оригінальних позначеннях
Dnipro. Аргументи працюють у ручному/автоматичному виключенні та
часових координатах. `examples.dae_inputs` будує справжню часову MNA
від `VoltageSource(source_value=u)`, зберігає $\dot u$ в реконструкції
й перевіряє весь перехід у Lean із явною регулярністю входу.

## Єдиний API та CLI часового конвеєра

З кореня Dnipro після встановлення обох пакетів:

```python
from pathlib import Path
from equireduce import LeanConfig
from dnipro.analysis import reduce_time_system, load_time_artifact

pipeline = reduce_time_system(
    "V1 in 0 U0\nR1 in out R\nC1 out 0 C",
    interval=(-1, 1), retain=("v_out",), assume_real=True,
    proof="require", lean=LeanConfig("EquiReduce/lean"),
)
equations = pipeline.equations             # tuple SymPy Eq, original labels
reconstruction = pipeline.reconstruction   # original labels
native = pipeline.reduction               # exact EquiReduce result and certificate
path = pipeline.export(Path("proofs/rc"))
restored = load_time_artifact(path)
```

Вхід — `Circuit`, часова `ResidualSystem`, текст netlist або `Path`
до файлу. `retain` задає назви функцій, які слід зберегти. Для ручного
виключення задайте `auto=False`; можна передати явні `differential`
та `algebraic`. `time` задає дійсний годинник; часові входи прив'язуються
через `input_sources={"V1": u}` без зміни переданого об'єкта схеми.
Початкові дані й параметри перевірки передаються через той самий виклик.
`provenance` зберігає незмінний знімок, карту позначень, імена рядків,
фізичні умови моделі, вибір гілок та явну політику дійсної області.
Незалежний EquiReduce може завантажити цей артефакт без імпорту Dnipro.

```bash
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real \
  --proof require --lean-project EquiReduce/lean --artifact proofs/rc
dnipro verify-dae proofs/rc --lean-project EquiReduce/lean
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output json
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output latex
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output lean
```

`--output lean` генерує доказ; тільки `--proof require` компілює його.
`verify-dae` завжди повторює символьну перевірку; з `--lean-project`
виконує нову компіляцію, без нього позначає минулий протокол як `recorded`.
`--manual`, `--max-candidates` і `--max-minors` керують вибором блоків.
`--input-source V1=u`, `--initial-time 0`, `--initial v_out=2`,
`--initial-input u=3`, `--initial-input-rate u=5`,
`--initial-param R=1` задають точні зразки; останній параметр стосується
початкової перевірки й не змінює рівняння всієї траєкторії.
Десяткові літерали й SPICE-суфікси парсяться як точні раціональні числа.
Числових розв'язувачів чи `--numeric` у команді `dae` немає.

## Конкретний зарядовий BJT

```bash
dnipro dae examples/dae_bjt.cir --interval -1 1 --list-branches
dnipro dae examples/dae_bjt.cir --interval -1 1 --retain v_b --retain v_c \
  --assume-real --branch 0:0 --proof require --lean-project EquiReduce/lean \
  --artifact proofs/bjt
```

`--branch POSITION:INDEX` посилається на детермінований список
`--list-branches`. У Python можна передати `branch_choices` як таку
мапу індексів або пари `(Piecewise, index)`. Без явного повного вибору
гілок конвеєр відхиляє `Piecewise`. Вибір діє на всьому інтервалі.

`build_equations(..., preserve_charges=True)` зберігає `Derivative(Q,t)`
для перевірки правила ланцюга. Новий єдиний API вмикає цей режим.
Стандартний старий режим побудови рівнянь не змінено. Метадані містять
умови фізичної області BJT, включно з позитивним фактором Ерлі.
Приклад має точні нормовані параметри, фіксований `VT`, `MJE=MJC=0`,
нелінійний заряд `TF/TR` та ефект Ерлі. Перевірено обидві полярності
й обидві гілки. Це не твердження про всі опції BJT: градуйовані переходи
з нецілими степенями, загальна квазінасиченість і події перемикання
не входять до заявленого формального профілю.

Приймання DN-DAE-10–12: 254 тести бібліотеки, 557 регресій Dnipro
для аналізу, MNA, parser, export, CLI та circuit, окремий фінальний
прогін 10 API/CLI-тестів після LaTeX-виправлення. Перевірено самостійний
wheel без Dnipro, відновлення старих артефактів і конкретного BJT,
а також нові компіляції RC/BJT через встановлений `verify-dae`.

## DC та стаціонарна проєкція

Адаптер знаходиться у Dnipro:
`dnipro/analysis/equireduce_adapter.py`. EquiReduce не імпортує Dnipro.
Dnipro тепер явно залежить від `equireduce==0.1.0.dev0`; обидва локальні
проєкти встановлюються разом:

```bash
python -m pip install -e ./EquiReduce -e .
```

```python
from dnipro.analysis.equireduce_adapter import from_dc_system

adapter = from_dc_system(residual_system, assume_real=True)
result = adapter.reduce()
original_labels = adapter.restore_reconstruction(result)
```

`from_dc_system` приймає лише `domain="dc"`. Невизначені припущення
Dnipro не стають дійсними мовчки: `assume_real=True` є явним вибором
дійсної області, а `real_domain_assumed` фіксує його використання.
Уже недійсні символи відхиляються. Початкові списки та символи не
змінюються. `symbol_map` показує відповідність позначень; параметри
визначаються з вільних символів системи й умов.

Для часової моделі є окрема операція:

```python
from dnipro.analysis.equireduce_adapter import stationary_from_time

adapter = stationary_from_time(time_system, assume_real=True)
assert adapter.origin == "stationary"
```

Вона зануляє лише оголошені перші похідні станів і будує рівняння
стаціонарного режиму. Області визначення читаються до занулення:
у `x′/(x-1)` умова `x != 1` не губиться. Зовнішня часова залежність,
невідомі та вищі похідні відхиляються. Знакові припущення станів
зберігаються; уявний стан не перетлумачується як дійсний.

Сертифікат такої проєкції стосується отриманої алгебраїчної системи.
Для відповідності часових траєкторій використовується окремий
`DAESystem` із [ДАЕ-контрактом](dae.md).

`dnipro.analysis.reduction` став шаром сумісності: збережено DC-домен,
схему результату, ідентичність старих символів та винятки Dnipro.
Алгоритми виключення, афінної декомпозиції та перевірки журналу
делегуються єдиному ядру EquiReduce. Дубльовані алгоритми видалено.
Для версії розробки міст використовує закріплений приватний формат
ядра; оновлення версії залежності потребуватиме перевірки сумісності.

Старий інтерфейс зберігає історичні символи без мовчазної зміни їх
ідентичності; новий явний контракт дійсної області доступний через
`from_dc_system`. Тепер і старий інтерфейс зберігає полюси джерела й
дозволяє виключити окремий афінний підблок зі збереженням нелінійного
залишку. Це може дати сильніше скорочення, ніж попередня реалізація.
Порівняльні регресії охоплюють контракти, сертифікати, пошук,
координати, метрики, артефакти та сумісність генератора Lean.
