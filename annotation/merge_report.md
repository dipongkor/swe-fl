# Annotation merge report

- Annotators: **Atish** vs **Eshgin**
- Instances considered: **31** (skipped 30 with ground truth)
- agree: **24**
- minor_conflict: **3**
- conflict: **2**
- single_annotator: **2**

## Blocking conflicts — need manual resolution (2)

### scikit-learn__scikit-learn-14983
- root causes: Atish=4, Eshgin=2, agreed=2
- **extra_location** (blocking)
    - only_in: Atish
    - file: sklearn/model_selection/_split.py
    - line: 1217
    - statement: KFold, n_repeats, random_state, n_splits=n_splits)
    - note: Continuation of RepeatedKFold.__init__'s super().__init__ call (starts line 1216): n_splits is declared as a named signature parameter - which _build_repr reflects over - but is demoted here into _RepeatedSplits' anonymous **cvargs dict without ever being stored as self.n_splits, breaking the store-params-as-attributes convention the repr machinery relies on. The storage side of the jointly-faulty pair with line 2160.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish
    - file: sklearn/model_selection/_split.py
    - line: 1270
    - statement: StratifiedKFold, n_repeats, random_state, n_splits=n_splits)
    - note: Same demotion in RepeatedStratifiedKFold.__init__ (call starts line 1269); exercised by the second test parametrization.
    - same_file_as_other_side: True

### sphinx-doc__sphinx-9602
- root causes: Atish=4, Eshgin=3, agreed=3
- **extra_location** (blocking)
    - only_in: Atish
    - file: sphinx/domains/python.py
    - line: 183
    - statement: result[i] = type_to_xref(str(node), env)
    - note: The action selected by line 182's classification: manufactures a py:class pending_xref for the token, so Literal values like True become unresolvable class references and nitpick mode (-n -W) fails the build with 'reference target not found: True'.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish': ['tests/test_domain_py.py:348  assert_node(doctree, ([pending_xref, "Literal"],'], 'Eshgin': ['tests/test_domain_py.py:348  assert_node(doctree, ([pending_xref, "Literal"],', 'tests/test_domain_py.py:356  assert_node(doctree, ([pending_xref, "typing.Literal"],']}

## Minor conflicts — likely same location (3)

### matplotlib__matplotlib-25960
- root causes: Atish=4, Eshgin=4, agreed=0
- **line_mismatch** (minor)
    - file: lib/matplotlib/figure.py
    - statement: dx = wr[self._subplotspec.colspan].sum() / wr.sum()
    - line_delta: 7
    - Atish: {'line': 2272, 'note': "Part of the four-line placement computation (lines 2272-2275) in SubFigure._redo_transform_rel_fig (def at line 2254), which derives a subfigure's relative bbox purely from the gridspec's width/height ratios; the gridspec's wspace/hspace never enter the arithmetic, so spacing passed to Figure.subfigures is stored in the GridSpec but ignored at placement time. This line computes the panel's width fraction: for the failing test's 2x3 grid with wspace=1/6 it yields 1/3 where the spacing-aware value is 0.3 (cells must shrink to leave gaps). The method's bbox parameter with its early-return (lines 2264-2267) exists at this revision but subfigures() never supplies it; the subfigures() call that forwards wspace/hspace into the GridSpec is itself innocent - the values are recorded, just never read back. Note the fix does not edit these lines: it compensates in subfigures() by computing spacing-aware cell boxes (gs.get_grid_positions) and passing them through the existing bbox parameter."}
    - Eshgin: {'line': 2279, 'note': 'The relative width is calculated only from GridSpec column ratios. This ignores the fraction of horizontal space reserved by wspace, so each subfigure remains too wide.'}
- **line_mismatch** (minor)
    - file: lib/matplotlib/figure.py
    - statement: dy = hr[self._subplotspec.rowspan].sum() / hr.sum()
    - line_delta: 7
    - Atish: {'line': 2273, 'note': "Same computation block: the panel's height fraction from row ratios only. For the failing test's 2 rows with hspace=0.5 it yields 1/2 where the spacing-aware value is 0.4."}
    - Eshgin: {'line': 2280, 'note': 'The relative height likewise uses only row ratios and omits the vertical space reserved by hspace.'}
- **line_mismatch** (minor)
    - file: lib/matplotlib/figure.py
    - statement: x0 = wr[:self._subplotspec.colspan.start].sum() / wr.sum()
    - line_delta: 7
    - Atish: {'line': 2274, 'note': "Same computation block: the panel's left edge as the ratio-sum of preceding columns, with no gap offsets. For the failing test, column 1 starts at 1/3 where the spacing-aware value is 0.35."}
    - Eshgin: {'line': 2281, 'note': 'The horizontal origin accumulates only preceding width ratios, so it does not include inter-column gaps requested through wspace.'}
- **line_mismatch** (minor)
    - file: lib/matplotlib/figure.py
    - statement: y0 = 1 - hr[:self._subplotspec.rowspan.stop].sum() / hr.sum()
    - line_delta: 7
    - Atish: {'line': 2275, 'note': "Same computation block: the panel's bottom edge from row ratio sums, with no gap offsets. This is the value the failing assertion observes directly: for the top row it yields 0.5 (bbox.min y = 240 on a 480-high figure) where the spacing-aware value is 0.6 (288)."}
    - Eshgin: {'line': 2282, 'note': 'The vertical origin accumulates only row ratios and therefore places rows contiguously instead of accounting for hspace.'}

### sympy__sympy-13877
- root causes: Atish=1, Eshgin=1, agreed=0
- **line_mismatch** (minor)
    - file: sympy/matrices/matrices.py
    - statement: if val:
    - line_delta: 1
    - Atish: {'line': 179, 'note': "Inside the _find_pivot helper (lines 177-181, a documented workaround for issue #12362) nested in _eval_det_bareiss, called from bareiss() at line 194. The pivot candidate is tested with plain truthiness, which only rejects entries that are structurally zero. A symbolic entry that is mathematically zero but not auto-simplified (e.g. 2*a*(a+2) + 2*a*(2*a+1) - 3*a*(2*a+2), produced during elimination of the rank-2 matrix [[i + a*j]]) passes this test and is selected as pivot. Bareiss fraction-free elimination divides each next-step entry by the previous pivot and is only exact when pivots are genuinely nonzero; a zero-equivalent pivot yields 0/0 terms, so det evaluates to nan (5x5 case) or raises TypeError 'Invalid NaN comparison' when cancel/factor_terms compares nan coefficients (6x6 case). The fix deletes _find_pivot and replaces the line-194 call with _find_reasonable_pivot(mat[:, 0], iszerofunc=_is_zero_after_expand_mul), where the new predicate expand_mul(x) == 0 correctly detects zero-equivalent polynomial entries."}
    - Eshgin: {'line': 180, 'note': 'The Bareiss-specific pivot finder treats a symbolic expression as a valid nonzero pivot solely from its truth value. A candidate can be structurally nonzero yet become zero after multiplication expansion, so selecting it as a pivot introduces invalid division and NaN into the recursive determinant calculation.'}
- _info_ ftcs_differs: {'Atish': ['sympy/matrices/tests/test_matrices.py:409  assert M(5).det() == 0', 'sympy/matrices/tests/test_matrices.py:410  assert M(6).det() == 0'], 'Eshgin': ['sympy/matrices/tests/test_matrices.py:409  assert M(5).det() == 0']}

### sympy__sympy-14248
- root causes: Atish=5, Eshgin=5, agreed=4
- **line_mismatch** (minor)
    - file: sympy/printing/str.py
    - statement: return ' + '.join([self.parenthesize(arg, precedence(expr))
    - line_delta: 1
    - Atish: {'line': 316, 'note': "StrPrinter._print_MatAdd (lines 315-317): joins terms with ' + ' unconditionally, never folding a term's negative coefficient into a '-' separator the way scalar _print_Add does, yielding '(-1)*B + (-1)*A*B + A'. Also inherited by all CodePrinter subclasses."}
    - Eshgin: {'line': 315, 'note': 'The matrix-sum printer always inserts a plus separator and never converts a negative term into subtraction. Code-printer subclasses inherit this behavior as well.'}
- _info_ ftcs_differs: {'Atish': ['sympy/printing/pretty/tests/test_pretty.py:6100  assert pretty(A*B*C - A*B - B*C) == "-A*B -B*C + A*B*C"', 'sympy/printing/tests/test_ccode.py:758  assert(ccode(F) == "(-B + A)[0]")', 'sympy/printing/tests/test_latex.py:1713  assert latex(F) == r"\\left(-B + A\\right)_{0, 0}"', 'sympy/printing/tests/test_latex.py:1722  assert latex(-A) == r"-A"', 'sympy/printing/tests/test_str.py:787  assert str(F) == "(-B + A)[0, 0]"', 'sympy/printing/tests/test_str.py:794  assert str(A - A*B - B) == "-B - A*B + A"'], 'Eshgin': ['sympy/printing/pretty/tests/test_pretty.py:6100  assert pretty(A*B*C - A*B - B*C) == "-A*B -B*C + A*B*C"', 'sympy/printing/tests/test_latex.py:1722  assert latex(-A) == r"-A"', 'sympy/printing/tests/test_latex.py:1723  assert latex(A - A*B - B) == r"-B - A B + A"', 'sympy/printing/tests/test_str.py:794  assert str(A - A*B - B) == "-B - A*B + A"']}

## Single-annotator instances (2)

### psf__requests-1724
- annotated only by **Eshgin** — merged as-is

### pydata__xarray-3993
- annotated only by **Atish** — merged as-is

## Full agreement on root cause (24)

### astropy__astropy-8707
- root causes: Atish=7, Eshgin=7, agreed=7

### django__django-11138
- root causes: Atish=4, Eshgin=4, agreed=4
- _info_ ftcs_differs: {'Atish': ['tests/timezones/tests.py:340  self.assertEqual(Event.objects.filter(dt__date=event_datetime.date()).first(), event)'], 'Eshgin': ['tests/timezones/tests.py:340  self.assertEqual(Event.objects.filter(dt__date=event_datetime.date()).first(), event)', 'tests/timezones/tests.py:346  self.assertEqual(Event.objects.filter(dt__date=datetime.date(2016, 1, 1)).first(), event)']}

### django__django-11532
- root causes: Atish=1, Eshgin=1, agreed=1
- _info_ ftcs_differs: {'Atish': ["tests/mail/tests.py:374  self.assertIn('@xn--p8s937b>', email.message()['Message-ID'])", 'tests/mail/tests.py:860  num_sent = mail.get_connection().send_messages([email])'], 'Eshgin': ["tests/mail/tests.py:374  self.assertIn('@xn--p8s937b>', email.message()['Message-ID'])"]}

### django__django-15572
- root causes: Atish=2, Eshgin=2, agreed=2

### matplotlib__matplotlib-25479
- root causes: Atish=2, Eshgin=2, agreed=2

### matplotlib__matplotlib-26466
- root causes: Atish=2, Eshgin=2, agreed=2

### pydata__xarray-3095
- root causes: Atish=1, Eshgin=1, agreed=1

### pydata__xarray-6938
- root causes: Atish=1, Eshgin=1, agreed=1

### pylint-dev__pylint-4604
- root causes: Atish=1, Eshgin=1, agreed=1

### pytest-dev__pytest-6197
- root causes: Atish=1, Eshgin=1, agreed=1

### pytest-dev__pytest-7236
- root causes: Atish=1, Eshgin=1, agreed=1

### pytest-dev__pytest-7324
- root causes: Atish=1, Eshgin=1, agreed=1

### scikit-learn__scikit-learn-10297
- root causes: Atish=2, Eshgin=2, agreed=2

### scikit-learn__scikit-learn-25973
- root causes: Atish=1, Eshgin=1, agreed=1

### scikit-learn__scikit-learn-9288
- root causes: Atish=1, Eshgin=1, agreed=1

### sphinx-doc__sphinx-10449
- root causes: Atish=2, Eshgin=2, agreed=2

### sphinx-doc__sphinx-11510
- root causes: Atish=1, Eshgin=1, agreed=1
- _info_ ftcs_differs: {'Atish': ['tests/test_directive_other.py:169  assert "baz/baz" in sources_reported', 'tests/test_directive_other.py:187  assert doctree.children[1].rawsource == "The amazing foo."'], 'Eshgin': ["tests/test_directive_other.py:166  restructuredtext.parse(app, text, 'index')", "tests/test_directive_other.py:183  doctree = restructuredtext.parse(app, text, 'index')"]}

### sphinx-doc__sphinx-8056
- root causes: Atish=2, Eshgin=2, agreed=2
- _info_ ftcs_differs: {'Atish': ['tests/test_ext_napoleon_docstring.py:1367  self.assertEqual(expected, actual)'], 'Eshgin': ['tests/test_ext_napoleon_docstring.py:1360  actual = str(NumpyDocstring(dedent(docstring), config))', 'tests/test_ext_napoleon_docstring.py:1367  self.assertEqual(expected, actual)']}

### sphinx-doc__sphinx-8551
- root causes: Atish=2, Eshgin=2, agreed=2

### sphinx-doc__sphinx-9320
- root causes: Atish=1, Eshgin=1, agreed=1

### sympy__sympy-15345
- root causes: Atish=1, Eshgin=1, agreed=1

### sympy__sympy-16597
- root causes: Atish=4, Eshgin=4, agreed=4

### sympy__sympy-19495
- root causes: Atish=2, Eshgin=2, agreed=2
- _info_ ftcs_differs: {'Atish': ['sympy/sets/tests/test_conditionset.py:127  assert ConditionSet(n, n < x, Interval(-oo, 0)).subs(x, p) == Interval(-oo, 0)', 'sympy/sets/tests/test_conditionset.py:137  assert ConditionSet(x, Contains(y, Interval(-1,1)), img1).subs(y, S.One/3).dummy_eq(img2)'], 'Eshgin': ['sympy/sets/tests/test_conditionset.py:None  assert ConditionSet(x, Contains( y, Interval(-1,1)), img1).subs(y, S.One/3).dummy_eq(img2)']}

### sympy__sympy-20438
- root causes: Atish=5, Eshgin=5, agreed=5
- _info_ ftcs_differs: {'Atish': ['sympy/sets/tests/test_sets.py:1254  assert Eq(ProductSet({1}, {2}), Interval(1, 2)) is S.false', 'sympy/sets/tests/test_sets.py:1604  assert b.is_subset(c) is True'], 'Eshgin': ['sympy/sets/tests/test_sets.py:1254  assert Eq(ProductSet({1}, {2}), Interval(1, 2)) is S.false', 'sympy/sets/tests/test_sets.py:1604  assert b.is_subset(c) is True', 'sympy/sets/tests/test_sets.py:1607  assert Eq(c, b).simplify() is S.true', 'sympy/sets/tests/test_sets.py:1609  assert Eq({1}, {x}).simplify() == Eq({1}, {x})']}

## Skipped (ground truth already exists)

- astropy__astropy-13579
- astropy__astropy-14365
- astropy__astropy-14598
- astropy__astropy-7671
- astropy__astropy-8872
- django__django-13121
- django__django-13449
- django__django-14007
- django__django-16145
- matplotlib__matplotlib-23299
- matplotlib__matplotlib-24026
- matplotlib__matplotlib-26208
- mwaskom__seaborn-3187
- psf__requests-2317
- psf__requests-2931
- pydata__xarray-3305
- pydata__xarray-4687
- pydata__xarray-6599
- pylint-dev__pylint-6386
- pylint-dev__pylint-6528
- pylint-dev__pylint-8898
- pytest-dev__pytest-5787
- pytest-dev__pytest-5840
- pytest-dev__pytest-7205
- scikit-learn__scikit-learn-12973
- scikit-learn__scikit-learn-14496
- scikit-learn__scikit-learn-26194
- sphinx-doc__sphinx-8548
- sphinx-doc__sphinx-9658
- sphinx-doc__sphinx-9711

