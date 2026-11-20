# Implemented API reference

This page is generated from the Python code of `0.1.0.dev0`. The design
contract and future additions are described separately in the [API guide](api.md).

## Systems and reduction

```{autoclass} equireduce.System
:members: algebraic
```

```{autofunction} equireduce.reduce_system
```

```{autofunction} equireduce.verify_certificate
```

```{autoclass} equireduce.ReductionResult
```

```{autoclass} equireduce.ReductionOptions
```

## Coordinates and search

```{autoclass} equireduce.AffineTransform
:members: create
```

```{autofunction} equireduce.reduce_in_coordinates
```

```{autofunction} equireduce.search_coordinates
```

```{autofunction} equireduce.benchmark_coordinates
```

```{autoclass} equireduce.metrics.ComplexityMetrics
```

```{autoclass} equireduce.search.SearchReport
```

## Experimental DAEs

```{autoclass} equireduce.DAESystem
:members: semi_explicit, interval_condition
```

```{autofunction} equireduce.reduce_dae
```

```{autofunction} equireduce.verify_dae_certificate
```

```{autoclass} equireduce.DAEReductionResult
:members: substitute_reconstructed_rates
```

```{autoclass} equireduce.RateSubstitution
```

```{autofunction} equireduce.verify_rate_substitution
```

## Implicit DAEs

```{autoclass} equireduce.SmoothFunction
:members: function, partials
```

```{autoclass} equireduce.ImplicitDAESystem
:members: create, input_regularity
```

```{autofunction} equireduce.analyze_implicit_dae
```

```{autofunction} equireduce.analyze_symbolic_rank
```

```{autofunction} equireduce.verify_implicit_structure
```

```{autofunction} equireduce.reduce_implicit_dae
```

```{autofunction} equireduce.verify_implicit_certificate
```

```{autoclass} equireduce.ImplicitDAEReductionResult
:members: required_input_rates
```

```{autofunction} equireduce.search_implicit_partitions
```

```{autoclass} equireduce.implicit_initial.ImplicitInitialCheck
```

```{autoclass} equireduce.implicit_search.ImplicitPartitionReport
```

```{autoclass} equireduce.TimeAffineTransform
:members: create
```

```{autofunction} equireduce.reduce_implicit_in_coordinates
```

```{autofunction} equireduce.verify_time_transform
```

```{autofunction} equireduce.verify_implicit_coordinate_certificate
```

## Lean

```{autoclass} equireduce.LeanConfig
```

```{autofunction} equireduce.generate_lean
```

```{autofunction} equireduce.verify_with_lean
```

## Artifacts

```{autofunction} equireduce.export_artifact
```

```{autofunction} equireduce.load_artifact
```
