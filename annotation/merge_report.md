# Annotation merge report

- Annotators: **Atish_Annotation** vs **Eshgin_Annotation**
- Instances considered: **130**
- agree: **94**
- conflict: **36**

## Per-location agreement

Root-cause locations are set-valued, so instance-level agree/conflict discards partial overlap. These score agreement per location; statement level is line-shift invariant and is the recommended headline number.

| Granularity | Jaccard (macro) | Jaccard (micro) | Dice / F1 (micro) | Krippendorff α (MASI) |
|---|---|---|---|---|
| file | 0.964 | 0.933 | 0.966 | 0.957 |
| statement | 0.817 | 0.721 | 0.838 | 0.781 |
| line | 0.817 | 0.716 | 0.835 | 0.781 |
| full | 0.817 | 0.716 | 0.835 | 0.781 |

Disagreement composition (76 conflicting locations): **extra_location** 76 (100%)

## Blocking conflicts — need manual resolution (36)

### django__django-11728
- root causes: Atish_Annotation=4, Eshgin_Annotation=2, agreed=2
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/contrib/admindocs/utils.py
    - line: 173
    - statement: group_pattern_and_name.append((pattern[start:end + idx], group_name))
    - note: Body of the misplaced check: its slice end + idx is calibrated to the check-one-iteration-late placement (idx already points past the closing parenthesis). It is faulty jointly with line 172 — a fix that detects balance immediately after the decrement must also extend the slice (the gold code uses end + idx + 1) — the pair encodes the same off-by-one-iteration scheme.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/contrib/admindocs/utils.py
    - line: 205
    - statement: group_indices.append((start, start + 1 + idx))
    - note: Joint partner of line 204, exactly as 173 is of 172: the start + 1 + idx end index presumes the late check (gold uses start + 2 + idx after moving the check below the decrement).
    - same_file_as_other_side: True

### django__django-13121
- root causes: Atish_Annotation=1, Eshgin_Annotation=3, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/expressions.py
    - line: 60
    - statement: other = DurationValue(other, output_field=fields.DurationField())
    - note: Timedelta literals in expressions were wrapped in the special DurationValue class instead of a normal Value with a DurationField output_field. On non-native-duration backends, DurationValue rendered the literal as backend-specific interval SQL rather than a normal duration parameter.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/expressions.py
    - line: 452
    - statement: if (not connection.features.has_native_duration_field and ((lhs_output and lhs_output.get_internal_type() == 'DurationField') or (rhs_output and rhs_output.get_internal_type() == 'DurationField'))):
    - note: CombinedExpression routed any expression with a DurationField operand through DurationExpression, including duration + duration. That path is only needed when combining a duration with a non-duration temporal value; for duration-only arithmetic it produced SQL/conversion behavior that broke SQLite and MySQL.
    - same_file_as_other_side: True
- _info_ confidence_differs: {'Atish_Annotation': 'medium', 'Eshgin_Annotation': 'high'}
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/expressions/tests.py:1424  test_set = [e.name for e in Experiment.objects.filter(start__lt=F('assigned') + delay)]", "tests/expressions/tests.py:1473  qs = Experiment.objects.annotate(duration=F('estimated_time') + delta)"], 'Eshgin_Annotation': ["tests/expressions/tests.py:1473  qs = Experiment.objects.annotate(duration=F('estimated_time') + delta)", 'tests/expressions/tests.py:1475  self.assertEqual(obj.duration, obj.estimated_time + delta)']}
- _info_ multi_rc_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### django__django-13158
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/sql/query.py
    - line: 288
    - statement: def clone(self):
    - note: Absence anchor, not a faulty statement: clone() shallow-copies __dict__ (line 296) and then explicitly re-copies every attribute that cannot be shared (297-307: alias maps, where, annotations, ...), but combined_queries is missing from that list, so a clone shares the SAME mutable subquery objects with the original. That violates clone's independence contract, and it becomes load-bearing the moment emptiness is propagated into the subqueries: verified empirically by applying only the set_empty recursion to base — the test's first assert then passes but the second fails, because qs3.none() (operating on a clone) emptied the shared subqueries and the original qs3 returned [] instead of [0, 1, 8, 9]. The gold patch adds the deep copy of combined_queries here.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/sql/query.py
    - line: 296
    - statement: obj.__dict__ = self.__dict__.copy()
    - note: A combined query clone retains the same component Query objects, so later empty-state changes cannot be isolated and applied as part of the cloned combined expression.
    - same_file_as_other_side: True

### django__django-13195
- root causes: Atish_Annotation=4, Eshgin_Annotation=5, agreed=4
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/http/response.py
    - line: 213
    - statement: def delete_cookie(self, key, path='/', domain=None):
    - note: The deletion API accepts no SameSite value, so callers cannot reproduce that attribute on the expiring Set-Cookie header.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/responses/test_cookie.py:131  response.delete_cookie('c', samesite='lax')", 'tests/sessions_tests/tests.py:797  str(response.cookies[settings.SESSION_COOKIE_NAME])'], 'Eshgin_Annotation': ["tests/messages_tests/test_cookie.py:89  self.assertEqual( response.cookies['messages']['samesite'], settings.SESSION_COOKIE_SAMESITE, )", "tests/responses/test_cookie.py:127  self.assertIs(response.cookies['c']['secure'], True)", "tests/responses/test_cookie.py:132  self.assertEqual(response.cookies['c']['samesite'], 'lax')", 'tests/sessions_tests/tests.py:759  self.assertEqual( \'Set-Cookie: {}=""; expires=Thu, 01 Jan 1970 00:00:00 GMT; \' \'Max-Age=0; Path=/; SameSite={}\'.format( settings.SESSION_COOKIE_NAME, settings.SESSION_COOKIE_SAMESITE, ), str(response.cookies[settings.SESSION_COOKIE_NAME]) )']}

### django__django-13343
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/files.py
    - line: 232
    - statement: self.storage = self.storage()
    - note: In FileField.__init__'s callable-storage branch. Evaluating the callable here is intended (the field needs a working Storage at runtime), but the assignment overwrites the only reference to the declared callable without recording it anywhere — mutation without record, the pytest-7571 shape — so by the time deconstruct runs, the information it is contractually required to reproduce no longer exists on the field. Jointly with line 282 this produces the fault; every adequate fix must retain the callable at this point (the gold patch stores it as _storage_callable just before this line) or stop overwriting it. The isinstance validation at 233-237 is faithful.
    - same_file_as_other_side: True

### django__django-13346
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/json.py
    - line: 482
    - statement: KeyTransform.register_lookup(KeyTransformExact)
    - note: Absence anchor, not a faulty statement: the KeyTransform lookup registry (lines 482-496) registers backend-aware specializations for exact, iexact, isnull, the string lookups, and the comparisons — but no KeyTransformIn class exists or is registered, so value__key__in resolves through the fallback to the generic lookups.In of the JSONField output_field. That fallback is not correct here: on backends without a native JSON type (SQLite, MySQL/MariaDB, Oracle) the KeyTransform LHS compiles to JSON_EXTRACT-style SQL yielding decoded JSON values, while In's rhs parameters remain the JSON-encoded text that JSONField.get_db_prep_value produces ('14', '"bar"', ...), so the IN comparison is text-vs-value and never matches. KeyTransformExact (class at line 381) embodies exactly the rhs treatment 'in' needs — wrapping each parameter in JSON_EXTRACT(%s, '$') (with vendor variants) so both sides are in the same representation — and the gold patch adds KeyTransformIn with that same process_rhs and registers it immediately before this line. Registry-is-the-semantics: the wrong-fallback gap, not any modified base line, is the fault.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/query_utils.py
    - line: 183
    - statement: return self.output_field.get_lookup(lookup_name)
    - note: A JSON key transform without its own in lookup falls back to the output field's generic lookup. That lookup does not prepare each right-hand JSON value in the representation required by backends without native JSON support.
    - same_file_as_other_side: False
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/model_fields/test_jsonfield.py:644  self.assertSequenceEqual('], 'Eshgin_Annotation': ['tests/model_fields/test_jsonfield.py:None  self.assertSequenceEqual( NullableJSONModel.objects.filter(**{lookup: value}), expected, )']}

### django__django-13449
- root causes: Atish_Annotation=1, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/expressions.py
    - line: 1335
    - statement: def as_sqlite(self, compiler, connection):
    - note: Window lacked a SQLite-specific rendering path for DecimalField output.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/expressions_window/tests.py:219  self.assertQuerysetEqual(qs, [...])'], 'Eshgin_Annotation': ["tests/expressions_window/tests.py:214  qs = Employee.objects.annotate(lag=Window(expression=Lag(expression='bonus', offset=1), partition_by=F('department'), order_by=[F('bonus').asc(), F('name').asc()]))", 'tests/expressions_window/tests.py:219  self.assertQuerysetEqual(qs, [...], transform=lambda row: (row.name, row.bonus, row.department, row.lag))']}

### django__django-14007
- root causes: Atish_Annotation=1, Eshgin_Annotation=3, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/sql/compiler.py
    - line: 1415
    - statement: return self.connection.ops.fetch_returned_insert_rows(cursor)
    - note: InsertCompiler returned database-provided inserted rows directly, bypassing field converters for returning_fields. Custom AutoField subclasses with from_db_value therefore received raw database integers after bulk_create.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/sql/compiler.py
    - line: 1419
    - statement: return [(self.connection.ops.last_insert_id(cursor, self.query.get_meta().db_table, self.query.get_meta().pk.column),)]
    - note: The fallback last_insert_id path also returned a raw primary-key value, so even create() on backends without RETURNING skipped from_db_value for the inserted primary key.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/custom_pk/tests.py:237  self.assertIsInstance(obj.id, MyWrapper)'], 'Eshgin_Annotation': ['tests/custom_pk/tests.py:236  obj = CustomAutoFieldModel.objects.create()', 'tests/custom_pk/tests.py:237  self.assertIsInstance(obj.id, MyWrapper)']}

### django__django-14315
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/backends/postgresql/client.py
    - line: 54
    - statement: return args, env
    - note: Tail of DatabaseClient.settings_to_cmd_args_env: env is built up from {} (line 39) with PG-specific vars added only when configured, so with no password/service/ssl/passfile settings it returns the empty dict. Under the runshell consumer's None-means-inherit interface this is the wrong sentinel: {} reads as 'use this as the entire child environment'. Jointly faulty with base/client.py line 24 — the producer emits an ambiguous falsy dict and the consumer misinterprets it; the dbshell tests (test_nopass, test_parameters) pin this return to None independently of the consumer-side fix. The env-building lines 39-53 are faithful accumulation.
    - same_file_as_other_side: False
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/backends/base/test_client.py:30  run.assert_called_once_with([], env=None, check=True)', 'tests/dbshell/test_postgresql.py:42  None,'], 'Eshgin_Annotation': ['tests/backends/base/test_client.py:30  run.assert_called_once_with([], env=None, check=True)']}

### django__django-14434
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/backends/base/schema.py
    - line: 1254
    - statement: columns = self._index_columns(table, columns, col_suffixes=(), opclasses=opclasses)
    - note: The other half of the interface fault: forwards the Table instance into _index_columns, which constructs Columns(table, ...) expecting the table name string (the issue's literal description). An alternative adequate fix leaves 1244 alone and passes model._meta.db_table here instead — one of the two lines must change, and neither is innocent in combination: the pair delivers a wrongly-typed value across a string-typed interface.
    - same_file_as_other_side: True

### django__django-15128
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/sql/query.py
    - line: 576
    - statement: change_map = {}
    - note: Absence anchor in Query.combine: the rhs-to-lhs alias relabel map is built while both queries still share the same alias namespace (both use the default 'T' prefix), and nothing separates the namespaces first. The loop below walks rhs.alias_map and, for each rhs join, self.join(...) mints the next free lhs alias — which, when lhs's table_map already contains the rhs table names, can be exactly another alias that rhs also uses: e.g. rhs alias T4 maps to freshly created T5 while rhs alias T5 maps to T6, so change_map = {'T4': 'T5', 'T5': 'T6'} has intersecting keys and values. That violates the documented precondition of change_aliases, whose assert at line 849 (a faithful guard — sequential application of a non-disjoint map would rename T4 to T5 and then that T5 on to T6) crashes the whole OR/AND combination with a bare AssertionError. Every adequate fix must guarantee domain/codomain disjointness before relabelling; the gold patch inserts rhs.bump_prefix(self, exclude={initial_alias}) right at this point, renaming rhs's aliases to a fresh prefix except the shared base-table alias. The per-join calls in the loop are individually faithful (the collision is a composite effect); the get_initial_alias() call at 594 is merely relocated by the fix (its value captured for the exclude set); and bump_prefix (line 882) was correct at base for its subquery use — its new exclude parameter and outer_query-to-other_query rename are fix plumbing and cosmetics.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/sql/query.py
    - line: 615
    - statement: change_map[alias] = new_alias
    - note: Alias remapping is accumulated without ensuring that source and destination alias sets are disjoint. A later source alias can equal an earlier destination, making relabeling ambiguous and violating Query.change_aliases() invariants.
    - same_file_as_other_side: True

### django__django-16256
- root causes: Atish_Annotation=9, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 788
    - statement: def create(self, **kwargs):
    - note: Absence anchor, not a faulty statement: in create_reverse_many_to_one_manager's RelatedManager (class line 638), this sync override injects kwargs[self.field.name] = self.instance, but no acreate shadows it. The manager therefore inherits the QuerySet-derived acreate (Manager methods generated from QuerySet), which runs plain QuerySet.create via sync_to_async — creating the object without the foreign key to the parent instance. Witnessed by test_acreate_reverse.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 796
    - statement: def get_or_create(self, **kwargs):
    - note: Absence anchor: same RelatedManager; no aget_or_create shadows this FK-injecting override, so the inherited QuerySet aget_or_create creates unlinked objects. Witnessed by test_aget_or_create_reverse (relatedmodel_set.acount() stays 0).
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 804
    - statement: def update_or_create(self, **kwargs):
    - note: Absence anchor: same RelatedManager; no aupdate_or_create shadows this override. Witnessed by test_aupdate_or_create_reverse.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 1186
    - statement: def create(self, *, through_defaults=None, **kwargs):
    - note: Absence anchor: in create_forward_many_to_many_manager's ManyRelatedManager (class line 949), the sync create creates the object and self.add()s it through the m2m table; with no acreate shadow, the inherited QuerySet acreate creates the object but never writes the through row (and accepts no through_defaults). Witnessed by test_acreate: the created object is invisible to the relation, so the follow-up aget() raises DoesNotExist.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 1194
    - statement: def get_or_create(self, *, through_defaults=None, **kwargs):
    - note: Absence anchor: same ManyRelatedManager; no aget_or_create shadow (get-or-create then add through row). Witnessed by test_aget_or_create (acount() returns 0 after aget_or_create reports created=True).
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/db/models/fields/related_descriptors.py
    - line: 1207
    - statement: def update_or_create(self, *, through_defaults=None, **kwargs):
    - note: Absence anchor: same ManyRelatedManager; no aupdate_or_create shadow. Witnessed by test_aupdate_or_create.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/contrib/contenttypes/fields.py
    - line: 741
    - statement: def create(self, **kwargs):
    - note: Absence anchor: in create_generic_related_manager's GenericRelatedObjectManager (class line 564), the sync create injects the content_type and object_id kwargs; with no acreate shadow, the inherited QuerySet acreate runs QuerySet.create without them, violating the NOT NULL constraints. Witnessed by test_generic_async_acreate (IntegrityError-class failure).
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/contrib/contenttypes/fields.py
    - line: 750
    - statement: def get_or_create(self, **kwargs):
    - note: Absence anchor: same GenericRelatedObjectManager; no aget_or_create shadow. Witnessed by test_generic_async_aget_or_create (create branch dies without content_type/object_id).
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: django/contrib/contenttypes/fields.py
    - line: 758
    - statement: def update_or_create(self, **kwargs):
    - note: Absence anchor: same GenericRelatedObjectManager; no aupdate_or_create shadow. Witnessed by test_generic_async_aupdate_or_create.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: django/db/models/manager.py
    - line: 87
    - statement: return getattr(self.get_queryset(), name)(*args, **kwargs)
    - note: The generated manager proxy sends inherited async creation methods directly to a plain related queryset. That bypasses the related manager's synchronous overrides, which inject foreign-key, many-to-many, or generic-relation state.
    - same_file_as_other_side: False
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/async/test_async_related_managers.py:13  await self.mtm1.simples.acreate(field=2)', 'tests/generic_relations/tests.py:49  await self.bacon.tags.acreate(tag="orange")'], 'Eshgin_Annotation': ['tests/async/test_async_related_managers.py:13  await self.mtm1.simples.acreate(field=2)']}

### matplotlib__matplotlib-22719
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: lib/matplotlib/category.py
    - line: 233
    - statement: if convertible:
    - note: Same vacuous-truth shape in UnitData.update: convertible is initialized True (line 224) and only demoted inside the per-value loop, so for empty data it stays vacuously True and the guard emits the 'plotting a list of strings that are all parsable as floats or dates' info log about data containing no strings at all. Not witnessed by the failing test: at base the empty-data path short-circuits at the convert guard (lines 61-66) before unit.update is reached, and a log record would not trip the warnings filter — but the statement is faulty at base by the same contract (log only when convertible strings were actually passed).
    - same_file_as_other_side: True

### matplotlib__matplotlib-24637
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: lib/matplotlib/offsetbox.py
    - line: 1443
    - statement: def draw(self, renderer):
    - note: Anchors an absence, not a faulty statement: AnnotationBbox.draw renders the artist entirely through its child artists (self.arrow_patch.draw, self.patch.draw, self.offsetbox.draw at lines 1453-1455) and at no point communicates the AnnotationBbox's own gid to the renderer. Composite artists propagate their gid by bracketing their child draws in renderer.open_group(..., gid=self.get_gid()) / renderer.close_group(...), which the SVG backend turns into a <g id=...> element; this method has no such bracketing, so a gid set via set_gid exists on the artist but never reaches the output. The child draw calls themselves are faithful, since each child correctly emits its own (unset) gid.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: lib/matplotlib/offsetbox.py
    - line: 1461
    - statement: self.offsetbox.draw(renderer)
    - note: AnnotationBbox draws its component artists directly without opening a renderer group for the enclosing artist. Vector renderers therefore receive the children but never receive the AnnotationBbox gid that should identify their containing group.
    - same_file_as_other_side: True

### matplotlib__matplotlib-26208
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: lib/matplotlib/axes/_base.py
    - line: 4444
    - statement: return ax2
    - note: ax2 is returned without copying ax1.xaxis.units to ax2.xaxis.units. ax2.xaxis.units remains None, causing unit conversion failures and dataLim corruption on ax1 when data is later plotted on ax2.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: lib/matplotlib/axes/_base.py
    - line: 4473
    - statement: return ax2
    - note: Same omission in twiny(): ax2 is returned without copying ax1.yaxis.units to ax2.yaxis.units.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: lib/matplotlib/axes/_base.py
    - line: 4442
    - statement: ax2.xaxis.set_visible(False)
    - note: twinx created an axes sharing the x-axis but did not copy the original xaxis units to the hidden twin x-axis. With categorical/unit-converted data, the twin axis could operate without the converter state expected by the shared axis machinery.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: lib/matplotlib/axes/_base.py
    - line: 4472
    - statement: ax2.yaxis.set_visible(False)
    - note: twiny had the symmetric omission for y-axis units, leaving the twin y-axis without the original axis units.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['lib/matplotlib/tests/test_axes.py:391  ax2 = getattr(ax1, twin_func)()'], 'Eshgin_Annotation': ['lib/matplotlib/tests/test_axes.py:389  ax1.plot(a, b)', 'lib/matplotlib/tests/test_axes.py:391  ax2 = getattr(ax1, twin_func)()']}

### pydata__xarray-3305
- root causes: Atish_Annotation=2, Eshgin_Annotation=3, agreed=2
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: xarray/core/variable.py
    - line: 1595
    - statement: def quantile(self, q, dim=None, interpolation="linear"):
    - note: Variable.quantile had no keep_attrs parameter, so callers could not request attribute preservation at the variable reduction layer.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['xarray/tests/test_dataarray.py:2306  actual = DataArray(self.va).quantile(q, dim=dim, keep_attrs=True)'], 'Eshgin_Annotation': ['xarray/tests/test_dataarray.py:2306  actual = DataArray(self.va).quantile(q, dim=dim, keep_attrs=True)', 'xarray/tests/test_dataarray.py:2311  assert actual.attrs == self.attrs']}

### pydata__xarray-4687
- root causes: Atish_Annotation=1, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: xarray/core/computation.py
    - line: 1812
    - statement: apply_ufunc(..., dask="allowed") without keep_attrs=keep_attrs
    - note: The old implementation also did not pass an attrs policy to apply_ufunc, so even an accepted API would have dropped attrs instead of preserving attrs from x.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['xarray/tests/test_computation.py:1929  actual = xr.where(cond, x, y, keep_attrs=True)'], 'Eshgin_Annotation': ['xarray/tests/test_computation.py:1929  actual = xr.where(cond, x, y, keep_attrs=True)', 'xarray/tests/test_computation.py:1931  assert_identical(expected, actual)']}
- _info_ multi_rc_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### pydata__xarray-6992
- root causes: Atish_Annotation=3, Eshgin_Annotation=2, agreed=2
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: xarray/core/dataset.py
    - line: 4169
    - statement: if drop:
    - note: Anchors an absence: this is the only per-name disposition logic in the reset_index loop, and it has no path that converts a de-indexed coordinate from IndexVariable to a plain Variable. After the index is removed (line 4172 filters it out), coordinates that survive keep their IndexVariable wrapper backed by the now-removed pandas index, an inconsistent state in the post-index-refactor data model where IndexVariable is supposed to correspond to an existing index.
    - same_file_as_other_side: True
- _info_ confidence_differs: {'Atish_Annotation': 'medium', 'Eshgin_Annotation': 'high'}
- _info_ ftcs_differs: {'Atish_Annotation': ['xarray/tests/test_dataset.py:3285  assert len(reset.dims) == 0', 'xarray/tests/test_dataset.py:3314  assert_identical(reset[name].variable, ds[name].variable.to_base_variable())'], 'Eshgin_Annotation': ['xarray/tests/test_dataset.py:3285  assert len(reset.dims) == 0']}

### pylint-dev__pylint-6386
- root causes: Atish_Annotation=1, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: pylint/config/utils.py
    - line: 211
    - statement: "-v": (False, _set_verbose_mode),
    - note: The PREPROCESSABLE_OPTIONS dictionary was missing the '-v' short form entry. Without it, passing '-v' on the command line was never intercepted during preprocessing and fell through to argparse, which saw a misconfigured option expecting a value and raised 'expected one argument'.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/config/test_config.py:107  Run([str(EMPTY_MODULE), '-v'], exit=False)"], 'Eshgin_Annotation': ['tests/config/test_config.py:107  Run([str(EMPTY_MODULE), "-v"], exit=False)']}
- _info_ multi_rc_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### pytest-dev__pytest-5787
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/reports.py
    - line: 181
    - statement: return {'reprcrash': reprcrash, 'reprtraceback': reprtraceback, 'sections': rep.longrepr.sections}
    - note: chain is never included in the serialized dict. For ExceptionChainRepr, this silently drops all chained exception entries.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: src/_pytest/reports.py
    - line: 192
    - statement: d["longrepr"] = disassembled_report(self)
    - note: The inner disassembled_report() function inside _to_json serializes longrepr by extracting only reprtraceback, reprcrash, and sections. It never inspects whether longrepr is an ExceptionChainRepr and never serializes the 'chain' attribute, which holds all the chained exception entries. For a chained exception, only the outermost traceback is preserved; all prior exceptions in the chain are silently dropped during serialization.
    - same_file_as_other_side: True
- _info_ confidence_differs: {'Atish_Annotation': 'medium', 'Eshgin_Annotation': 'high'}
- _info_ ftcs_differs: {'Atish_Annotation': ['testing/test_reports.py:306  data = report._to_json()', 'testing/test_reports.py:307  loaded_report = report_class._from_json(data)'], 'Eshgin_Annotation': ['testing/test_reports.py:308  check_longrepr(loaded_report.longrepr)']}

### pytest-dev__pytest-5840
- root causes: Atish_Annotation=1, Eshgin_Annotation=2, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/config/__init__.py
    - line: 457
    - statement: self._conftestpath2mod[conftestpath] = mod
    - note: Stores the conftest module using a py.path.local key (after unique_path normalization). The test looks up using a pathlib.Path key via Path().resolve(), so the lookup fails despite the conftest being loaded.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: src/_pytest/config/__init__.py
    - line: 415
    - statement: for parent in directory.parts():
    - note: Iterating directory.parts() without first calling realpath() means symlinks in the directory path are never resolved before walking up the hierarchy to find conftest.py files. Without this, conftest.py files reachable only via symlink are never discovered.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: src/_pytest/pathlib.py
    - line: 346
    - statement: return type(path)(normcase(str(path.realpath())))
    - note: unique_path() normalizes paths via normcase(), which on case-insensitive but case-preserving file systems such as Windows lowercases the entire path string. When this lowercased path is used to import conftest modules, Python cannot find the package because the real directory name differs in case (e.g. 'PIsys' becomes 'pisys'), directly causing ModuleNotFoundError.
    - same_file_as_other_side: False
- _info_ ftcs_differs: {'Atish_Annotation': ['src/_pytest/config/__init__.py:420  mod = self._importconftest(conftestpath)', 'testing/test_conftest.py:167  conftest_setinitial(conftest, [sub.dirpath()], confcutdir=testdir.tmpdir)'], 'Eshgin_Annotation': ['testing/test_conftest.py:170  assert key in conftest._conftestpath2mod']}
- _info_ multi_rc_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### pytest-dev__pytest-7490
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/skipping.py
    - line: 257
    - statement: yield
    - note: Anchors an absence, not a faulty statement: pytest_runtest_call is the hookwrapper that brackets the test body, and after this yield returns nothing re-evaluates the item's xfail marks. The stored evaluation (item._store[xfailed_key]) is produced only before the body runs, at setup (line 242) or pre-yield (lines 249-251), so a mark added dynamically during the test via request.node.add_marker is never seen: the store keeps the pre-call result None. The downstream consumer in pytest_runtest_makereport (line 264, xfailed = item._store.get(xfailed_key, None)) is a faithful reader of the store; with the stale None it skips both the failed-becomes-xfail branch (lines 279-286) and the strict-xpass branch (lines 287-290). A re-evaluation anywhere between the end of the test body and that read would supply the missing information; this line marks the start of that span.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: src/_pytest/skipping.py
    - line: 251
    - statement: item._store[xfailed_key] = xfailed = evaluate_xfail_marks(item)
    - note: The call hook evaluates and caches xfail state before the test body runs. A marker added by the test body is therefore absent from the cached value later consumed by report generation, and the hook does not refresh that value after execution.
    - same_file_as_other_side: True

### pytest-dev__pytest-7571
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/logging.py
    - line: 356
    - statement: for logger_name, level in self._initial_logger_levels.items():
    - note: Anchors an absence, not a faulty statement in itself: _finalize's restore section ('This restores the log levels changed by set_level') iterates only the recorded logger levels; no statement restores the handler level that set_level also changed. Jointly faulty with line 437: between them the invariant that every level set_level changes is undone at teardown is broken for the handler.
    - same_file_as_other_side: True

### pytest-dev__pytest-8399
- root causes: Atish_Annotation=5, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/python.py
    - line: 531
    - statement: name=f"xunit_setup_module_fixture_{self.obj.__name__}",
    - note: Same fault for the auto-generated fixture wrapping xunit-style setup_module/teardown_module: no leading underscore, so the internal fixture is public and shown by plain --fixtures. Not reached by the failing test, which only defines a unittest.TestCase.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/python.py
    - line: 560
    - statement: name=f"xunit_setup_function_fixture_{self.obj.__name__}",
    - note: Same fault for the fixture wrapping xunit-style setup_function/teardown_function. Not reached by the failing test.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/python.py
    - line: 812
    - statement: name=f"xunit_setup_class_fixture_{self.obj.__qualname__}",
    - note: Same fault for the fixture wrapping xunit-style setup_class/teardown_class. Not reached by the failing test.
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: src/_pytest/python.py
    - line: 841
    - statement: name=f"xunit_setup_method_fixture_{self.obj.__qualname__}",
    - note: Same fault for the fixture wrapping xunit-style setup_method/teardown_method. Not reached by the failing test.
    - same_file_as_other_side: False

### scikit-learn__scikit-learn-14496
- root causes: Atish_Annotation=1, Eshgin_Annotation=3, agreed=1
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sklearn/cluster/optics_.py
    - line: 622
    - statement: min_samples = max(2, min_samples * n_samples)
    - note: The xi extraction path independently retains a float after converting fractional min_samples, although subsequent steep-region indexing and counts require an integer.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sklearn/cluster/optics_.py
    - line: 627
    - statement: min_cluster_size = max(2, min_cluster_size * n_samples)
    - note: Fractional min_cluster_size is likewise retained as a float and passed into cluster boundary calculations that require a sample count.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ["sklearn/cluster/tests/test_optics.py:107  clust = OPTICS(min_samples=0.1, min_cluster_size=0.08, max_eps=20, cluster_method='xi', xi=0.4).fit(X)"], 'Eshgin_Annotation': ['sklearn/cluster/tests/test_optics.py:108  assert_array_equal(clust.labels_, expected_labels)']}

### scikit-learn__scikit-learn-14629
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sklearn/multioutput.py
    - line: 300
    - statement: class MultiOutputClassifier(MultiOutputEstimator, ClassifierMixin):
    - note: Anchors an absence, not a faulty statement: the class exposes no classes_ attribute anywhere. It is a ClassifierMixin, and fitted sklearn classifiers are expected to expose classes_ (multi-output ones as a list of per-output arrays: multi-output RandomForestClassifier does, and ClassifierChain.fit sets self.classes_ at line 586). After the inherited MultiOutputEstimator.fit (line 124) fits the per-target estimators into self.estimators_ (line 167), the per-output class labels exist only on self.estimators_[i].classes_ and are never aggregated onto the wrapper. The class's own predict_proba docstring (line 345) even states the returned probability columns are ordered as 'in the attribute classes_'. Any consumer reading the documented attribute, e.g. cross_val_predict(method='predict_proba'), gets AttributeError.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sklearn/multioutput.py
    - line: 167
    - statement: self.estimators_ = Parallel(n_jobs=self.n_jobs)(
    - note: The inherited fitting path stores the fitted classifier for each output but exposes no aggregate class-label metadata on the wrapper. MultiOutputClassifier consequently finishes fitting with estimators_ only, although classifier consumers expect its classes_ attribute to describe the classes for every output.
    - same_file_as_other_side: True

### scikit-learn__scikit-learn-14983
- root causes: Atish_Annotation=4, Eshgin_Annotation=2, agreed=2
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sklearn/model_selection/_split.py
    - line: 1217
    - statement: KFold, n_repeats, random_state, n_splits=n_splits)
    - note: Continuation of RepeatedKFold.__init__'s super().__init__ call (starts line 1216): n_splits is declared as a named signature parameter - which _build_repr reflects over - but is demoted here into _RepeatedSplits' anonymous **cvargs dict without ever being stored as self.n_splits, breaking the store-params-as-attributes convention the repr machinery relies on. The storage side of the jointly-faulty pair with line 2160.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sklearn/model_selection/_split.py
    - line: 1270
    - statement: StratifiedKFold, n_repeats, random_state, n_splits=n_splits)
    - note: Same demotion in RepeatedStratifiedKFold.__init__ (call starts line 1269); exercised by the second test parametrization.
    - same_file_as_other_side: True

### scikit-learn__scikit-learn-25747
- root causes: Atish_Annotation=2, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sklearn/utils/_set_output.py
    - line: 58
    - statement: if index is not None:
    - note: Jointly faulty with line 59: this branch of _wrap_in_pandas_container handles data that is already a DataFrame, and the guard's only semantics is 'whenever the caller supplied an index, enact the overwrite on line 59'. The wrapper is always called with index=getattr(original_input, 'index', None), so for DataFrame input the overwrite is unconditional.
    - same_file_as_other_side: True

### sphinx-doc__sphinx-8548
- root causes: Atish_Annotation=4, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sphinx/ext/autodoc/importer.py
    - line: 312
    - statement: namespace = '.'.join(objpath)
    - note: Namespace hardcoded to target subclass path. Even if moved inside the MRO loop, superclass attr_docs entries would never match.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sphinx/ext/autodoc/importer.py
    - line: 314
    - statement: if namespace == ns and name not in members:
    - note: 
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sphinx/ext/autodoc/importer.py
    - line: 315
    - statement: members[name] = ClassAttribute(subject, name, INSTANCEATTR,
    - note: 
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sphinx/ext/autodoc/__init__.py
    - line: 1587
    - statement: members = get_class_members(self.object, self.objpath, self.get_attr, self.analyzer)
    - note: The call site passes self.analyzer, which is the analyzer for the subject class only. This is the externally-scoped single-analyzer that the buggy 'if analyzer:' block in importer.py depends on, reinforcing the MRO-blindness.
    - same_file_as_other_side: False
- _info_ confidence_differs: {'Atish_Annotation': 'medium', 'Eshgin_Annotation': 'high'}
- _info_ ftcs_differs: {'Atish_Annotation': ['sphinx/ext/autodoc/__init__.py:1587  members = get_class_members(self.object, self.objpath, self.get_attr, self.analyzer)', 'tests/test_ext_autodoc_autoclass.py:83  assert list(actual) == [...]'], 'Eshgin_Annotation': ["tests/test_ext_autodoc_autoclass.py:82  actual = do_autodoc(app, 'class', 'target.instance_variable.Bar', options)"]}

### sphinx-doc__sphinx-9602
- root causes: Atish_Annotation=4, Eshgin_Annotation=3, agreed=3
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sphinx/domains/python.py
    - line: 183
    - statement: result[i] = type_to_xref(str(node), env)
    - note: The action selected by line 182's classification: manufactures a py:class pending_xref for the token, so Literal values like True become unresolvable class references and nitpick mode (-n -W) fails the build with 'reference target not found: True'.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_domain_py.py:348  assert_node(doctree, ([pending_xref, "Literal"],'], 'Eshgin_Annotation': ['tests/test_domain_py.py:348  assert_node(doctree, ([pending_xref, "Literal"],', 'tests/test_domain_py.py:356  assert_node(doctree, ([pending_xref, "typing.Literal"],']}

### sympy__sympy-13031
- root causes: Atish_Annotation=4, Eshgin_Annotation=2, agreed=2
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/matrices/sparse.py
    - line: 1195
    - statement: return type(self)(other)
    - note: Body of the misplaced guard in row_join, jointly faulty with 1194: replacing the accumulated matrix by a copy of other discards self's column count. Any adequate fix must stop this replacement for dimension-carrying zero-size operands.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/matrices/sparse.py
    - line: 989
    - statement: return type(self)(other)
    - note: Body of the col_join guard, jointly faulty with 988: discards self's row count by replacing the accumulator with other.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/matrices/tests/test_sparse.py:31  assert SparseMatrix.hstack(*sparse_matrices) == Matrix(0, 6, [])'], 'Eshgin_Annotation': ['sympy/matrices/tests/test_sparse.py:31  assert SparseMatrix.hstack(*sparse_matrices) == Matrix(0, 6, [])', 'sympy/matrices/tests/test_sparse.py:33  assert SparseMatrix.vstack(*sparse_matrices) == Matrix(6, 0, [])']}

### sympy__sympy-18698
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=0
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/polys/polytools.py
    - line: 5953
    - statement: return coeff, factors
    - note: Absence anchor, not a faulty statement: the end of _symbolic_factor_list, which for method='sqf' emits the per-argument results without any normalization step. The loop above decomposes each Mul argument of the unexpanded input separately and concatenates the per-arg (factor, multiplicity) pairs — each append (lines 5925, 5934-5951) is faithful for its own argument — but nothing merges factors that share a multiplicity across arguments, so sqf_list((x**2+1)*(x-1)**2*(x-2)**3*(x-3)**3) returns two distinct multiplicity-3 entries instead of the canonical single square-free part per multiplicity ((x-2)*(x-3) = x**2-5x+6, 3) that the dense sqf algorithm produces for the expanded polynomial. Every adequate fix must add that merge before emission (the gold patch groups by multiplicity right here) or restructure to decompose the product as a whole. The patch's removal of the arg.is_Mul flattening block (base lines 5908-5910) is unwitnessed hygiene — no failing test presents a nested Mul argument — and the import changes are plumbing.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sympy/polys/polytools.py
    - line: 5908
    - statement: if arg.is_Mul: args.extend(arg.args) continue
    - note: The symbolic square-free path flattens a product into independent arguments before factoring them, so factors with the same multiplicity are emitted separately instead of being combined into one square-free factor.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/polys/tests/test_polytools.py:3276  assert sqf_list(x*(x + y)) == (1, [(x**2 + x*y, 1)])', 'sympy/polys/tests/test_polytools.py:3340  assert sqf_list(p) == result'], 'Eshgin_Annotation': ['sympy/polys/tests/test_polytools.py:3340  assert sqf_list(p) == result']}

### sympy__sympy-19783
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/physics/quantum/dagger.py
    - line: 13
    - statement: class Dagger(adjoint):
    - note: Absence anchor, not a faulty statement: the Dagger class defines no __mul__, so Dagger(O) * IdentityOperator() uses Expr's default multiplication and builds an unevaluated Mul. Plain operators absorb the identity on this side through Operator.__mul__ (operator.py lines 181-182, returning self when other is an IdentityOperator); Dagger, not being an Operator subclass, has no counterpart of that absorption, which the gold patch adds as Dagger.__mul__. Witnessed by Dagger(O) * I == Dagger(O) and by test_dagger_mul's Dagger(O)*Dagger(I) (Dagger of the Hermitian identity already evaluates to I at base, so it exercises the same product).
    - same_file_as_other_side: False
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sympy/core/expr.py
    - line: 203
    - statement: return Mul(self, other)
    - note: Dagger inherits the generic Expr multiplication fallback, which always constructs Mul and does not recognize a right-side IdentityOperator.
    - same_file_as_other_side: False
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/physics/quantum/tests/test_dagger.py:39  assert Dagger(O)*Dagger(I) == Dagger(O)', 'sympy/physics/quantum/tests/test_operator.py:97  assert I * Dagger(O) == Dagger(O)'], 'Eshgin_Annotation': ['sympy/physics/quantum/tests/test_operator.py:97  assert I * Dagger(O) == Dagger(O)', 'sympy/physics/quantum/tests/test_operator.py:98  assert Dagger(O) * I == Dagger(O)']}

### sympy__sympy-21596
- root causes: Atish_Annotation=5, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/sets/handlers/intersection.py
    - line: 311
    - statement: base_set -= ConditionSet(n, Eq(im, 0), S.Integers)
    - note: Same inversion on the fallback branch (im's factored solutions not all linear in n): it subtracts the set where im vanishes — precisely the set that should become the base set. Reached at base by the rational-im test cases, which line 307 misroutes here.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/sets/handlers/intersection.py
    - line: 307
    - statement: x, xis = zip(*[solve_linear(i, 0) for i in Mul.make_args(im) if n in i.free_symbols])
    - note: Collects candidate solutions of im = 0 from ALL Mul factors of im. For a rational im such as (n - 3)*(n + 1)/(2*n + 2), the reciprocal denominator factor contains n but has no root, so solve_linear yields a non-n result, the all-linear check at 308 fails, and solvable cases are misrouted to the ConditionSet fallback. The fix solves only the factors of numer(im); under the test's expectations (exact FiniteSet results for rational im) every adequate fix must likewise exclude denominator factors here. The check at 308 itself is a faithful consumer.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/sets/handlers/intersection.py
    - line: 315
    - statement: sol = list(zip(*[solve_linear(i, 0) for i in Mul.make_args(im) if n in i.free_symbols]))
    - note: In the denominator-exclusion loop ('exclude values that make denominators 0'): the comprehension's loop variable i shadows the outer i (the denominator from denoms(f)), so this line re-solves the IMAGINARY PART's factors instead of the denominator whose poles it is supposed to find. The denominator's roots are never computed on this branch, so poles are not excluded whenever im has factors containing n.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/sets/handlers/intersection.py
    - line: 319
    - statement: base_set -= FiniteSet(xis)
    - note: Here subtraction is the semantically correct operation (excluding poles), but the statement subtracts the wrong values (im-roots, from line 315) and repeats the tuple-wrapping defect — FiniteSet(xis) contains one tuple element, so nothing is ever removed from an integer base set and pole exclusion is a silent no-op. The ConditionSet fallback at 321 is faithful by contrast (it subtracts the poles of the actual outer denominator i) and survives semantically in the fix via _solution_union(denoms(f), n).
    - same_file_as_other_side: True

### sympy__sympy-21930
- root causes: Atish_Annotation=3, Eshgin_Annotation=1, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/physics/secondquant.py
    - line: 942
    - statement: return "a^\\dagger_{%s}" % self.state.name
    - note: Same fault in CreateFermion._latex for the fermion creation operator a^\dagger_{p}. Reached by test_create_f, test_commutation, and test_NO.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/physics/secondquant.py
    - line: 221
    - statement: return "%s^{%s}_{%s}" % (
    - note: Same fault in AntiSymmetricTensor._latex: the tensor prints as t^{ab}_{ij} unbraced, so raising it to a power likewise yields a double superscript. Reached by test_Tensors.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ["sympy/physics/tests/test_secondquant.py:534  assert latex(tabij) == '{t^{ab}_{ij}}'", "sympy/physics/tests/test_secondquant.py:1260  assert latex(Commutator(Bd(a)**2, B(a)) ) == '- \\\\left[b_{0},{b^\\\\dagger_{0}}^{2}\\\\right]'"], 'Eshgin_Annotation': ["sympy/physics/tests/test_secondquant.py:None  assert latex(Commutator(Bd(a)**2, B(a)) ) == '- \\\\left[b_{0},{b^\\\\dagger_{0}}^{2}\\\\right]'"]}

### sympy__sympy-22080
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=1
- **extra_location** (blocking)
    - only_in: Atish_Annotation
    - file: sympy/printing/precedence.py
    - line: 27
    - statement: PRECEDENCE_VALUES = {
    - note: Anchors an absence: the PRECEDENCE_VALUES table, which IS the parenthesization semantics for printers, has no 'Mod' entry, so a Mod expression falls back to function-call precedence (70, above Mul's 50). Code printers render Mod as the binary % operator, whose real Python/C precedence is the multiplication level, so any printer that asks whether an embedded Mod needs parentheses concludes it never does. Inside a Mul this yields e.g. '-x % y', which Python parses as '(-x) % y'.
    - same_file_as_other_side: True
- **extra_location** (blocking)
    - only_in: Eshgin_Annotation
    - file: sympy/printing/precedence.py
    - line: 134
    - statement: return PRECEDENCE_VALUES[n]
    - note: Mod has no direct precedence entry, so the MRO lookup reaches Function and assigns function-call precedence to an expression printed with the infix % operator. Its operands are consequently not grouped according to multiplicative precedence.
    - same_file_as_other_side: True
- _info_ ftcs_differs: {'Atish_Annotation': ["sympy/codegen/tests/test_rewriting.py:269  assert cc(-x**4) == '-(x*x*x*x)'", "sympy/printing/tests/test_pycode.py:33  assert prntr.doprint(-Mod(x, y)) == '-(x % y)'", 'sympy/utilities/tests/test_lambdify.py:275  assert no_modules(3, 7) == -3'], 'Eshgin_Annotation': ["sympy/printing/tests/test_pycode.py:33  assert prntr.doprint(-Mod(x, y)) == '-(x % y)'", "sympy/printing/tests/test_pycode.py:34  assert prntr.doprint(Mod(-x, y)) == '(-x) % y'", 'sympy/utilities/tests/test_lambdify.py:274  assert no_modules(3, 7) == empty_modules(3, 7)']}

## Full agreement on root cause (94)

### astropy__astropy-13579
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['astropy/wcs/wcsapi/wrappers/tests/test_sliced_wcs.py:935  out_pix = sl.world_to_pixel_values(world[0], world[1])'], 'Eshgin_Annotation': ['astropy/wcs/wcsapi/wrappers/tests/test_sliced_wcs.py:933  sl = SlicedLowLevelWCS(fits_wcs, 0)', 'astropy/wcs/wcsapi/wrappers/tests/test_sliced_wcs.py:935  out_pix = sl.world_to_pixel_values(world[0], world[1])']}

### astropy__astropy-14365
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ["astropy/io/ascii/tests/test_qdp.py:93  table = _read_table_qdp(path, names=['MJD', 'Rate'], table_id=0)"], 'Eshgin_Annotation': ['astropy/io/ascii/tests/test_qdp.py:84  example_qdp = lowercase_header(example_qdp)', 'astropy/io/ascii/tests/test_qdp.py:93  table = _read_table_qdp(path, names=["MJD", "Rate"], table_id=0)']}

### astropy__astropy-14598
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ confidence_differs: {'Atish_Annotation': 'high', 'Eshgin_Annotation': 'medium-high'}
- _info_ ftcs_differs: {'Atish_Annotation': ['astropy/io/fits/tests/test_header.py:589  assert c.value == testval'], 'Eshgin_Annotation': ['astropy/io/fits/card.py:533  m = self._strg_comment_RE.match(vc)', 'astropy/io/fits/card.py:537  value = m.group("strg") or ""', 'astropy/io/fits/tests/test_header.py:586  testval = "x" * 100 + "\'\'"', 'astropy/io/fits/tests/test_header.py:588  c = fits.Card.fromstring(c.image)']}

### astropy__astropy-7606
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### astropy__astropy-7671
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['astropy/utils/tests/test_introspection.py:73  assert minversion(test_module, version)'], 'Eshgin_Annotation': ["astropy/utils/tests/test_introspection.py:70  good_versions = ['0.12', '0.12.1', '0.12.0.dev', '0.12dev']"]}

### astropy__astropy-8707
- root causes: Atish_Annotation=7, Eshgin_Annotation=7, agreed=7

### astropy__astropy-8872
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['astropy/units/tests/test_quantity.py:146  q3_16 = u.Quantity(a3_16, u.yr)'], 'Eshgin_Annotation': ['astropy/units/tests/test_quantity.py:145  a3_16 = np.array([1., 2.], dtype=np.float16)', 'astropy/units/tests/test_quantity.py:147  assert q3_16.dtype == a3_16.dtype']}

### django__django-10554
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-11138
- root causes: Atish_Annotation=4, Eshgin_Annotation=4, agreed=4
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/timezones/tests.py:340  self.assertEqual(Event.objects.filter(dt__date=event_datetime.date()).first(), event)'], 'Eshgin_Annotation': ['tests/timezones/tests.py:340  self.assertEqual(Event.objects.filter(dt__date=event_datetime.date()).first(), event)', 'tests/timezones/tests.py:346  self.assertEqual(Event.objects.filter(dt__date=datetime.date(2016, 1, 1)).first(), event)']}

### django__django-11265
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/filtered_relation/tests.py:102  self.assertSequenceEqual('], 'Eshgin_Annotation': ["tests/filtered_relation/tests.py:None  self.assertSequenceEqual( Author.objects.annotate( book_alice=FilteredRelation('book', condition=Q(book__title__iexact='poem by alice')), ).exclude(book_alice__isnull=False), [self.author2], )"]}

### django__django-11400
- root causes: Atish_Annotation=3, Eshgin_Annotation=3, agreed=3
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/admin_filters/tests.py:744  def test_relatedonlyfieldlistfilter_foreignkey_ordering(self):', 'tests/model_fields/tests.py:248  self.field.get_choices(include_blank=False),'], 'Eshgin_Annotation': ['tests/admin_filters/tests.py:769  self.assertEqual(filterspec.lookup_choices, expected)']}

### django__django-11532
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/mail/tests.py:374  self.assertIn('@xn--p8s937b>', email.message()['Message-ID'])", 'tests/mail/tests.py:860  num_sent = mail.get_connection().send_messages([email])'], 'Eshgin_Annotation': ["tests/mail/tests.py:374  self.assertIn('@xn--p8s937b>', email.message()['Message-ID'])"]}

### django__django-11734
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/queries/tests.py:2817  self.assertTrue(qs.exists())'], 'Eshgin_Annotation': ['tests/queries/tests.py:2817  self.assertTrue(qs.exists())', 'tests/queries/tests.py:2819  self.assertFalse(qs.exists())']}

### django__django-11740
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/migrations/test_autodetector.py:2260  changes = self.get_changes([self.author_empty, self.book_with_no_author_fk], [self.author_empty, self.book])'], 'Eshgin_Annotation': ["tests/migrations/test_autodetector.py:2266  self.assertMigrationDependencies(changes, 'otherapp', 0, [('testapp', '__first__')])"]}

### django__django-12155
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-12406
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/model_forms/tests.py:289  list(form.fields['character'].choices)"], 'Eshgin_Annotation': ["tests/model_forms/test_modelchoicefield.py:157  self.assertEqual( list(f.choices), [('', '---------')] + choices if blank else choices, )", "tests/model_forms/tests.py:288  self.assertEqual( list(form.fields['character'].choices), [(character.pk, 'user')], )"]}

### django__django-13297
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-13344
- root causes: Atish_Annotation=4, Eshgin_Annotation=4, agreed=4

### django__django-13512
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/admin_utils/tests.py:196  self.assertEqual(display_for_field(value, models.JSONField(), self.empty_value), display_value)', 'tests/forms_tests/field_tests/test_jsonfield.py:32  self.assertEqual(field.prepare_value(\'你好，世界\'), \'"你好，世界"\')'], 'Eshgin_Annotation': ['tests/admin_utils/tests.py:194  self.assertEqual(', 'tests/forms_tests/field_tests/test_jsonfield.py:32  self.assertEqual(field.prepare_value(\'你好，世界\'), \'"你好，世界"\')']}

### django__django-13810
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/middleware_exceptions/tests.py:190  response = await self.async_client.get('/middleware_exceptions/view/')"], 'Eshgin_Annotation': ["tests/middleware_exceptions/tests.py:193  self.assertEqual( cm.records[0].getMessage(), 'Asynchronous middleware middleware_exceptions.tests.MyMiddleware ' 'adapted.', )"]}

### django__django-14011
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ confidence_differs: {'Atish_Annotation': 'high', 'Eshgin_Annotation': 'medium'}

### django__django-14034
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-14053
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### django__django-14170
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### django__django-14349
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ confidence_differs: {'Atish_Annotation': 'high', 'Eshgin_Annotation': 'medium'}

### django__django-15503
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/model_fields/test_jsonfield.py:601  self.assertSequenceEqual('], 'Eshgin_Annotation': ['tests/model_fields/test_jsonfield.py:601  self.assertSequenceEqual( NullableJSONModel.objects.filter(condition), [obj], )']}

### django__django-15554
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-15563
- root causes: Atish_Annotation=3, Eshgin_Annotation=3, agreed=3
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/model_inheritance_regress/tests.py:674  Congressman.objects.update(title="senator 1")'], 'Eshgin_Annotation': ['tests/model_inheritance_regress/tests.py:675  self.assertEqual(Congressman.objects.get().title, "senator 1")', 'tests/model_inheritance_regress/tests.py:681  self.assertEqual(Senator.objects.get().title, "senator 1")']}

### django__django-15572
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### django__django-15629
- root causes: Atish_Annotation=4, Eshgin_Annotation=4, agreed=4

### django__django-15732
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/migrations/test_operations.py:2871  operation.database_forwards(app_label, editor, project_state, new_state)'], 'Eshgin_Annotation': ['tests/migrations/test_operations.py:2873  self.assertConstraintNotExists(table_name, unique_together_constraint_name)']}

### django__django-15916
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/model_forms/tests.py:3522  NewForm = modelform_factory(model=Person, form=BaseForm)'], 'Eshgin_Annotation': ['tests/model_forms/tests.py:3510  self.assertEqual(type(field.widget), forms.Textarea)', 'tests/model_forms/tests.py:3528  self.assertEqual(type(field.widget), forms.Textarea)']}

### django__django-16145
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/admin_scripts/tests.py:1593  call_command('runserver', addrport='0:8000', use_reloader=False, skip_checks=True, stdout=self.output)"], 'Eshgin_Annotation': ['tests/admin_scripts/tests.py:1593  call_command("runserver", addrport="0:8000", use_reloader=False, skip_checks=True, stdout=self.output)', 'tests/admin_scripts/tests.py:1600  self.assertIn("Starting development server at http://0.0.0.0:8000/", self.output.getvalue())']}

### django__django-16315
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/bulk_create/tests.py:793  FieldsWithDbColumns.objects.bulk_create('], 'Eshgin_Annotation': ['tests/bulk_create/tests.py:None  self.assertCountEqual( FieldsWithDbColumns.objects.values("rank", "name"), [ {"rank": 1, "name": "c"}, {"rank": 2, "name": "d"}, ], )']}

### django__django-16454
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ confidence_differs: {'Atish_Annotation': 'high', 'Eshgin_Annotation': 'medium'}

### django__django-16502
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/servers/test_basehttp.py:152  WSGIRequestHandler(request, "192.168.0.2", server)'], 'Eshgin_Annotation': ['tests/servers/test_basehttp.py:158  self.assertEqual(body, b"\\r\\n")']}

### django__django-16631
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### django__django-16901
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/xor_lookups/tests.py:30  self.assertCountEqual('], 'Eshgin_Annotation': ['tests/xor_lookups/tests.py:None  self.assertCountEqual( qs, self.numbers[1:3] + self.numbers[5:7] + self.numbers[9:], )']}

### django__django-16938
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/serializers/tests.py:411  def test_serialize_only_pk(self):'], 'Eshgin_Annotation': ['tests/serializers/tests.py:None  serializers.serialize( self.serializer_name, Article.objects.all(), use_natural_foreign_keys=False, )']}

### django__django-17084
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/aggregation/tests.py:2221  aggregate = total_books_qs.aggregate(sum_avg_publisher_pages=Sum("avg_publisher_pages"), books_count=Count("id"))'], 'Eshgin_Annotation': ['tests/aggregation/tests.py:2226  self.assertEqual(sql.count("select"), 2, "Subquery wrapping required")']}

### matplotlib__matplotlib-20859
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### matplotlib__matplotlib-23299
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['lib/matplotlib/tests/test_rcparams.py:501  with mpl.rc_context():'], 'Eshgin_Annotation': ["lib/matplotlib/tests/test_rcparams.py:501  with mpl.rc_context(): mpl.rcParams['backend'] = 'module://aardvark'", "lib/matplotlib/tests/test_rcparams.py:503  assert mpl.rcParams['backend'] == 'module://aardvark'"]}

### matplotlib__matplotlib-24026
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["lib/matplotlib/tests/test_axes.py:2858  ax.stackplot('x', 'y1', 'y2', 'y3', data=data, colors=['C0', 'C1', 'C2'])"], 'Eshgin_Annotation': ['lib/matplotlib/tests/test_axes.py:2858  ax.stackplot("x", "y1", "y2", "y3", data=data, colors=["C0", "C1", "C2"])']}

### matplotlib__matplotlib-25287
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### matplotlib__matplotlib-25311
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### matplotlib__matplotlib-25479
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### matplotlib__matplotlib-25960
- root causes: Atish_Annotation=4, Eshgin_Annotation=4, agreed=4

### matplotlib__matplotlib-26466
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### mwaskom__seaborn-3187
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/_core/test_plot.py:2057  p = Plot(**xy, color=color).add(MockMark()).plot()', "tests/test_relational.py:680  g = relplot(data=long_df, x='x', y='y', hue=long_df['z'] + 1e8)"], 'Eshgin_Annotation': ['tests/_core/test_plot.py:2057  p = Plot(**xy, color=color).add(MockMark()).plot()', 'tests/test_relational.py:680  g = relplot(data=long_df, x="x", y="y", hue=long_df["z"] + 1e8)']}

### psf__requests-2317
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### psf__requests-2931
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["test_requests.py:161  request = requests.Request('PUT', 'http://example.com', data=u'ööö'.encode('utf-8')).prepare()"], 'Eshgin_Annotation': ['test_requests.py:161  request = requests.Request(\'PUT\', \'http://example.com\', data=u"\\u00f6\\u00f6\\u00f6".encode("utf-8")).prepare()']}

### pydata__xarray-3095
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pydata__xarray-3993
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['xarray/tests/test_dataset.py:6607  da.integrate(dim="x")'], 'Eshgin_Annotation': ['xarray/tests/test_dataset.py:6606  with pytest.warns(FutureWarning): da.integrate(dim="x")']}

### pydata__xarray-6599
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['xarray/tests/test_computation.py:2035  actual = xr.polyval(coord=x, coeffs=coeffs)'], 'Eshgin_Annotation': ['xarray/tests/test_computation.py:2014  xr.DataArray(np.array([1000, 2000, 3000], dtype="timedelta64[ns]"), dims="x")', 'xarray/tests/test_computation.py:2017  xr.DataArray([0, 1], dims="degree", coords={"degree": [0, 1]})']}

### pydata__xarray-6938
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pydata__xarray-7229
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pylint-dev__pylint-4604
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pylint-dev__pylint-6528
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/lint/unittest_lint.py:879  run = Run(['--recursive', 'y', ignore_parameter, ignore_parameter_value, join(REGRTEST_DATA_DIR, 'directory')], exit=False)"], 'Eshgin_Annotation': ['tests/lint/unittest_lint.py:898  assert ignored_file not in linted_file_paths']}

### pylint-dev__pylint-8898
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["tests/config/test_config.py:165  Run([str(EMPTY_MODULE), r'--bad-names-rgx=(foo{1,}, foo{1,3}})'], exit=False)"], 'Eshgin_Annotation': ['tests/config/test_config.py:135  r = Run([str(EMPTY_MODULE), rf"--bad-names-rgx={in_string}"], exit=False)', 'tests/config/test_config.py:167  Run([str(EMPTY_MODULE), r"--bad-names-rgx=(foo{1,}, foo{1,3}})"], exit=False)']}

### pytest-dev__pytest-10051
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pytest-dev__pytest-6197
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pytest-dev__pytest-7205
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['src/_pytest/setuponly.py:35  _show_fixture_action(fixturedef, "SETUP")', 'testing/test_setuponly.py:315  assert result.ret == 0'], 'Eshgin_Annotation': ['testing/test_setuponly.py:None  result = testdir.run(sys.executable, "-bb", "-m", "pytest", "--setup-show", str(test_file))', 'testing/test_setuponly.py:None  result = testdir.runpytest(mode, p)', 'testing/test_setuponly.py:None  result = testdir.runpytest(mode, p)', 'testing/test_setuponly.py:None  result = testdir.runpytest(mode, p)']}
- _info_ multi_rc_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### pytest-dev__pytest-7236
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### pytest-dev__pytest-7324
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### scikit-learn__scikit-learn-10297
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### scikit-learn__scikit-learn-12973
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['sklearn/linear_model/tests/test_least_angle.py:718  lasso_lars.fit(X, y, copy_X=copy_X)'], 'Eshgin_Annotation': ['sklearn/linear_model/tests/test_least_angle.py:719  assert copy_X == np.array_equal(X, X_copy)']}

### scikit-learn__scikit-learn-13124
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### scikit-learn__scikit-learn-13142
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### scikit-learn__scikit-learn-25931
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### scikit-learn__scikit-learn-25973
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### scikit-learn__scikit-learn-26194
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['sklearn/metrics/tests/test_ranking.py:420  tpr, fpr, thresholds = roc_curve(y_true, y_score, drop_intermediate=True)', 'sklearn/metrics/tests/test_ranking.py:2214  _, _, thresholds = roc_curve(y_true, y_score)'], 'Eshgin_Annotation': ['sklearn/metrics/tests/test_ranking.py:421  assert_array_almost_equal(thresholds, [np.inf, 1.0, 0.7, 0.0])', 'sklearn/metrics/tests/test_ranking.py:None  _, _, thresholds = roc_curve(y_true, y_score) assert np.isinf(thresholds[0])']}

### scikit-learn__scikit-learn-9288
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sphinx-doc__sphinx-10449
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### sphinx-doc__sphinx-11510
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_directive_other.py:169  assert "baz/baz" in sources_reported', 'tests/test_directive_other.py:187  assert doctree.children[1].rawsource == "The amazing foo."'], 'Eshgin_Annotation': ["tests/test_directive_other.py:166  restructuredtext.parse(app, text, 'index')", "tests/test_directive_other.py:183  doctree = restructuredtext.parse(app, text, 'index')"]}

### sphinx-doc__sphinx-7462
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_domain_py.py:258  doctree = _parse_annotation("Tuple[()]")', 'tests/test_pycode_ast.py:57  ("()", "()"), # Tuple (empty)'], 'Eshgin_Annotation': ['tests/test_domain_py.py:258  doctree = _parse_annotation("Tuple[()]")', 'tests/test_pycode_ast.py:61  assert ast.unparse(module.body[0].value) == expected']}

### sphinx-doc__sphinx-7910
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_ext_napoleon.py:139  self.assertIs(_skip_member(app, what, member, obj, skip,', "tests/test_ext_napoleon.py:180  self.assertSkip('class', '__decorated_func__',"], 'Eshgin_Annotation': ["tests/test_ext_napoleon.py:None  self.assertSkip('class', '__decorated_func__', SampleClass.__decorated_func__, False, 'napoleon_include_special_with_doc')"]}

### sphinx-doc__sphinx-8056
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_ext_napoleon_docstring.py:1367  self.assertEqual(expected, actual)'], 'Eshgin_Annotation': ['tests/test_ext_napoleon_docstring.py:1360  actual = str(NumpyDocstring(dedent(docstring), config))', 'tests/test_ext_napoleon_docstring.py:1367  self.assertEqual(expected, actual)']}

### sphinx-doc__sphinx-8120
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sphinx-doc__sphinx-8475
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['tests/test_build_linkcheck.py:405  assert content == {'], 'Eshgin_Annotation': ['tests/test_build_linkcheck.py:None  assert content == { "code": 0, "status": "working", "filename": "index.rst", "lineno": 1, "uri": "http://localhost:7777/", "info": "", }']}

### sphinx-doc__sphinx-8551
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2

### sphinx-doc__sphinx-9320
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sphinx-doc__sphinx-9658
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ rc_ftcs_same_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### sphinx-doc__sphinx-9711
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ rc_ftcs_same_differs: {'Atish_Annotation': False, 'Eshgin_Annotation': True}

### sympy__sympy-13877
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/matrices/tests/test_matrices.py:409  assert M(5).det() == 0', 'sympy/matrices/tests/test_matrices.py:410  assert M(6).det() == 0'], 'Eshgin_Annotation': ['sympy/matrices/tests/test_matrices.py:409  assert M(5).det() == 0']}

### sympy__sympy-14248
- root causes: Atish_Annotation=5, Eshgin_Annotation=5, agreed=5
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/printing/pretty/tests/test_pretty.py:6100  assert pretty(A*B*C - A*B - B*C) == "-A*B -B*C + A*B*C"', 'sympy/printing/tests/test_ccode.py:758  assert(ccode(F) == "(-B + A)[0]")', 'sympy/printing/tests/test_latex.py:1713  assert latex(F) == r"\\left(-B + A\\right)_{0, 0}"', 'sympy/printing/tests/test_latex.py:1722  assert latex(-A) == r"-A"', 'sympy/printing/tests/test_str.py:787  assert str(F) == "(-B + A)[0, 0]"', 'sympy/printing/tests/test_str.py:794  assert str(A - A*B - B) == "-B - A*B + A"'], 'Eshgin_Annotation': ['sympy/printing/pretty/tests/test_pretty.py:6100  assert pretty(A*B*C - A*B - B*C) == "-A*B -B*C + A*B*C"', 'sympy/printing/tests/test_latex.py:1722  assert latex(-A) == r"-A"', 'sympy/printing/tests/test_latex.py:1723  assert latex(A - A*B - B) == r"-B - A B + A"', 'sympy/printing/tests/test_str.py:794  assert str(A - A*B - B) == "-B - A*B + A"']}

### sympy__sympy-15345
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sympy__sympy-15976
- root causes: Atish_Annotation=3, Eshgin_Annotation=3, agreed=3

### sympy__sympy-16597
- root causes: Atish_Annotation=4, Eshgin_Annotation=4, agreed=4

### sympy__sympy-16792
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sympy__sympy-17318
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sympy__sympy-19495
- root causes: Atish_Annotation=2, Eshgin_Annotation=2, agreed=2
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/sets/tests/test_conditionset.py:127  assert ConditionSet(n, n < x, Interval(-oo, 0)).subs(x, p) == Interval(-oo, 0)', 'sympy/sets/tests/test_conditionset.py:137  assert ConditionSet(x, Contains(y, Interval(-1,1)), img1).subs(y, S.One/3).dummy_eq(img2)'], 'Eshgin_Annotation': ['sympy/sets/tests/test_conditionset.py:None  assert ConditionSet(x, Contains( y, Interval(-1,1)), img1).subs(y, S.One/3).dummy_eq(img2)']}

### sympy__sympy-20438
- root causes: Atish_Annotation=5, Eshgin_Annotation=5, agreed=5
- _info_ ftcs_differs: {'Atish_Annotation': ['sympy/sets/tests/test_sets.py:1254  assert Eq(ProductSet({1}, {2}), Interval(1, 2)) is S.false', 'sympy/sets/tests/test_sets.py:1604  assert b.is_subset(c) is True'], 'Eshgin_Annotation': ['sympy/sets/tests/test_sets.py:1254  assert Eq(ProductSet({1}, {2}), Interval(1, 2)) is S.false', 'sympy/sets/tests/test_sets.py:1604  assert b.is_subset(c) is True', 'sympy/sets/tests/test_sets.py:1607  assert Eq(c, b).simplify() is S.true', 'sympy/sets/tests/test_sets.py:1609  assert Eq({1}, {x}).simplify() == Eq({1}, {x})']}

### sympy__sympy-21379
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1

### sympy__sympy-24562
- root causes: Atish_Annotation=1, Eshgin_Annotation=1, agreed=1
- _info_ ftcs_differs: {'Atish_Annotation': ["sympy/core/tests/test_numbers.py:372  assert Rational(p, q).as_numer_denom() == Rational('%s/%s'%(p,q)).as_numer_denom()"], 'Eshgin_Annotation': ["sympy/core/tests/test_numbers.py:375  assert Rational(p, q).as_numer_denom() == Rational('%s/%s'%(p,q)).as_numer_denom()", "sympy/core/tests/test_numbers.py:377  assert Rational('0.5', '100') == Rational(1, 200)"]}

