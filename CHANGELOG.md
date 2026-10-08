# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.0.0](https://github.com/Landparty/jcl-parser/compare/v1.4.0...v2.0.0) (2026-10-08)


### ⚠ BREAKING CHANGES

* registered plugins no longer run unless a ParserConfig enables them (pass ParserConfig(enabled_plugins=[ALL_PLUGINS]) for the old behaviour); validate_jcl and ParserConfig raise ValueError for an unknown validation level or dialect instead of ignoring it.
* parse_jcl("job.jcl") and other str sources are parsed as JCL text, never opened. Use parse_jcl(Path("job.jcl")).

### Features

* **program-profiles:** close common IBM/utility program coverage gaps ([d8c7f6f](https://github.com/Landparty/jcl-parser/commit/d8c7f6f2331c655bb52e4975020f9573f6e3c86b))


### Bug Fixes

* accept SPACE=(TRK,0) primary allocation ([#65](https://github.com/Landparty/jcl-parser/issues/65)) ([f4dd94e](https://github.com/Landparty/jcl-parser/commit/f4dd94e6b904cc149eef559adc923c0b5b7d7dbf))
* **analysis:** exact RC domain, not-run steps, NG/NL, lifecycle branches and referbacks ([922f024](https://github.com/Landparty/jcl-parser/commit/922f02402db11536c4ce7865a5bcb84e301c7abd))
* apply dataset dispositions at step end in lifecycle check ([#65](https://github.com/Landparty/jcl-parser/issues/65)) ([820d212](https://github.com/Landparty/jcl-parser/commit/820d212e2655d033a65c1923e7c82364b025287d))
* bound RC feasibility search by combination count ([#65](https://github.com/Landparty/jcl-parser/issues/65)) ([4d165f7](https://github.com/Landparty/jcl-parser/commit/4d165f77d8fdec09b4872cb143a602fd5f2ad097))
* **build:** avoid Cython compiler crash in dataset_lifecycle._merge_states ([7aef911](https://github.com/Landparty/jcl-parser/commit/7aef911fdb8fbf6c15ef764baa6d955a5080e08c))
* **cli:** print parameters in JCL syntax, not Python reprs ([0695b70](https://github.com/Landparty/jcl-parser/commit/0695b70479e86c4fe070260114ef813a2352bc65))
* close audit patch-release findings (C1-C6, H1, H2, H5, M3) ([944233b](https://github.com/Landparty/jcl-parser/commit/944233bd171b9bc1b5366c8f2d894913ac9bc266))
* **conditions:** stop truncating and inverting IF conditions ([e09453f](https://github.com/Landparty/jcl-parser/commit/e09453fbe017c32e98744de21b481135c0d89f36))
* **continuation:** report a suspect comment field once, not twice ([4f9f756](https://github.com/Landparty/jcl-parser/commit/4f9f756194077e5ac989541153d4461eef8b52fa))
* DCB override merge, concatenated DD member overrides, symbols in override DDs, CLI queries ([308b223](https://github.com/Landparty/jcl-parser/commit/308b223c60f2b0a58576db7d8088a4559b1fd38c))
* **dd:** read DSNAME= as the DD's dataset name ([4125f55](https://github.com/Landparty/jcl-parser/commit/4125f556e8bc67d7fadbb376725fd55e98c2c0b4))
* **disp:** read an omitted DISP status as NEW ([c468754](https://github.com/Landparty/jcl-parser/commit/c46875473b674004c6770014d8f3b1cc5291c477))
* **explosion:** apply EXEC keyword overrides to PROC steps ([1c35c21](https://github.com/Landparty/jcl-parser/commit/1c35c219e7f7c853362b72d07091a6ec31e7e52a))
* **explosion:** keep && temporary dataset names through explosion ([e41dfdd](https://github.com/Landparty/jcl-parser/commit/e41dfdd6525a9a8e947fab37818be2fc48f5df7d))
* **explosion:** merge PROC DD overrides instead of replacing the DD ([2356596](https://github.com/Landparty/jcl-parser/commit/235659612df1314524eccaf6d184c9e5102aed56))
* **explosion:** PROC SET scoping, JCLLIB loader in explode_job, EXEC override symbols ([b636924](https://github.com/Landparty/jcl-parser/commit/b6369241ce5250160b4957c980a375029b659986))
* **explosion:** qualify step references made inside a PROC ([1a8b476](https://github.com/Landparty/jcl-parser/commit/1a8b476338e684a11c02b0c52bc930ab06810b6d))
* file-type detection, value-first conditions, IDCAMS continuations, RECFM/BLKSIZE validation ([4041508](https://github.com/Landparty/jcl-parser/commit/404150868e2baa8b66c2aa02972bc0ddb98fd8b6))
* IF-statement parsing and DD overrides on conditional PROC steps ([02f7f7a](https://github.com/Landparty/jcl-parser/commit/02f7f7aa29f2a9a1e2afebb0c35e1de60c260876))
* INCLUDE inside in-stream data, quoted JCLLIB names, valid SARIF, abbreviated IDCAMS DEFINE ([d60be12](https://github.com/Landparty/jcl-parser/commit/d60be125e7befc2bcaea8c3da355289f7520c7a4))
* **include:** search JCLLIB libraries on continuation lines; warn on missing member ([73b9a2f](https://github.com/Landparty/jcl-parser/commit/73b9a2ff4e85de4f33c50561cf51fe436b1de7a2))
* **io:** parse JCL with a UTF-8 BOM; never treat JCL text as a path ([357d8cc](https://github.com/Landparty/jcl-parser/commit/357d8cc2fa81c23f163e00fe996f4d166d32b39c))
* JES comment fields, dynamnbr/perform crash, rc_analysis verdicts and speed, abnormal UNCATLG, SYSTSIN concatenation ([2703e57](https://github.com/Landparty/jcl-parser/commit/2703e5745813f674820de4f559fcc56361759e49))
* keep comment records inside a continued in-stream DD out of its data ([#58](https://github.com/Landparty/jcl-parser/issues/58)) ([00ec7b3](https://github.com/Landparty/jcl-parser/commit/00ec7b36b3069cb080e5f5325d906272c1e430bb))
* keep ContinuationLineHandler and utils helpers importable from parser ([beedc82](https://github.com/Landparty/jcl-parser/commit/beedc8204e8179cc9aa6433810e3677f91ad9211))
* keep significant blanks when a quoted string is continued ([#65](https://github.com/Landparty/jcl-parser/issues/65)) ([b1fa877](https://github.com/Landparty/jcl-parser/commit/b1fa877c154030075c203cef153780118d12b2b9))
* **lint:** don't flag symbolic dataset names as literal HLQs ([4031b96](https://github.com/Landparty/jcl-parser/commit/4031b9671453f5467dc897e525971e20416a7de9))
* make every ParserConfig field take effect ([#67](https://github.com/Landparty/jcl-parser/issues/67)) ([0412283](https://github.com/Landparty/jcl-parser/commit/041228373d8e31804cfaa27aea119e63079ef696))
* never read a str as a file; DLM= only on DD */DATA; bound PROC lookups ([a0c30c9](https://github.com/Landparty/jcl-parser/commit/a0c30c9cbac1935f4f09dc3fe4d982043a7786bd))
* **parser:** read a continued DD * / DD DATA statement before its data ([1e15e2f](https://github.com/Landparty/jcl-parser/commit/1e15e2f44a5d32147ba1f70458bf08f1c53b9b28))
* **parser:** read in-stream data with no DD as an implicit SYSIN ([27fe776](https://github.com/Landparty/jcl-parser/commit/27fe77612a3bc95c57c8db94290e4f27d68018eb))
* **parser:** stop silently dropping real-world JCL content ([e739f1d](https://github.com/Landparty/jcl-parser/commit/e739f1dd2a42fe06e6c9f5f95e84f9f9b95c8a05))
* **profiles:** read SYSTSIN like TSO when finding the program a wrapper runs ([05d8fb6](https://github.com/Landparty/jcl-parser/commit/05d8fb61e39db18a209928523e2758d0e8caa530))
* **program_profiles:** read PARM= as TSO control text, not just SYSTSIN ([e63171f](https://github.com/Landparty/jcl-parser/commit/e63171f6c2fb33639df195e25091239419b3f96a))
* **program-profiles:** derive DD events from the DISP the JCL states ([b1f102b](https://github.com/Landparty/jcl-parser/commit/b1f102bf52b9f1806ddb48c8df508b451c571fef))
* reject unknown characters and bare RC in IF conditions ([#63](https://github.com/Landparty/jcl-parser/issues/63)) ([4a841e3](https://github.com/Landparty/jcl-parser/commit/4a841e324592bed1920687c9f11472a3ac9224a2))
* report job.validate() errors from validate_jcl and --validate ([#57](https://github.com/Landparty/jcl-parser/issues/57)) ([1df9a2e](https://github.com/Landparty/jcl-parser/commit/1df9a2ec2aa3d15026ed727596ea77be5d1f898d))
* report OS errors from the CLI instead of a traceback ([#65](https://github.com/Landparty/jcl-parser/issues/65)) ([3385a32](https://github.com/Landparty/jcl-parser/commit/3385a32810daf17f87c7ee491e89120a7a75054d))
* resolve SET symbols in EXEC PGM= and PROC names ([5615641](https://github.com/Landparty/jcl-parser/commit/561564170c19b1c46f526173967b68395b1ef66b))
* SET redefinition scope, unqualified-override concatenation members, DFSRRC00 list PARM ([e5d8430](https://github.com/Landparty/jcl-parser/commit/e5d84308d5ea78087a1889be0bdb0ada2d60f578))
* split records on newlines only and decode cp1252 before latin-1 ([#62](https://github.com/Landparty/jcl-parser/issues/62)) ([2bb8ce7](https://github.com/Landparty/jcl-parser/commit/2bb8ce7b8154bf2daf374025780ca45b007f983f))
* **sql:** stop reporting utility control statements as SQL ([73a1944](https://github.com/Landparty/jcl-parser/commit/73a1944971e4bed384b570e65c5d85794fb1e001))
* stop reporting TSO DELETE/ALTER as embedded SQL in profiles ([#66](https://github.com/Landparty/jcl-parser/issues/66)) ([00d0a8a](https://github.com/Landparty/jcl-parser/commit/00d0a8a77fe0040e6c1e9c099553937d4c77ea77))
* **symbols:** keep system symbols through the parse-time SET pass ([d6888bd](https://github.com/Landparty/jcl-parser/commit/d6888bd3268a277a6ae856e68bf901775e6d4fcb))
* **symbols:** resolve symbol values that reference system symbols ([9dd42d3](https://github.com/Landparty/jcl-parser/commit/9dd42d3c229aade87330f57bc3273470018eb162))
* **symbols:** substitute parenthesised symbol values as JCL; don't crash on SET lists ([6bbe77e](https://github.com/Landparty/jcl-parser/commit/6bbe77e242b5c382d05be86b275764dc89810022))
* temp dataset DISP=MOD, catalog state in lifecycle checks, ValidationPlugin step/DD hooks, metrics referbacks ([177a966](https://github.com/Landparty/jcl-parser/commit/177a966505f36dd7bc5912f1a325a5936cf17b0b))
* treat RUN of an unknown step as unknown in RC analysis ([#61](https://github.com/Landparty/jcl-parser/issues/61)) ([0d2de0d](https://github.com/Landparty/jcl-parser/commit/0d2de0db496cf9e004e2cfd13f44c9a3a1aa61b6))
* **validation:** exploded step names, temp dataset re-creation, DISP status, JES comments ([cfa2804](https://github.com/Landparty/jcl-parser/commit/cfa2804b9da1e2dd1bc2d920a896edb61b9056c3))
* **validators:** accept DD DUMMY, work files, PDS members and (,CATLG) ([15d7800](https://github.com/Landparty/jcl-parser/commit/15d7800c4401bdf2b5a7392bf824b8ed13e53a32))
* walk IF branches separately for temporary dataset creation ([#60](https://github.com/Landparty/jcl-parser/issues/60)) ([3bce8cd](https://github.com/Landparty/jcl-parser/commit/3bce8cd3b5d58fb3e49e361d0ca25fcde5b3a0d0))
* warn when a PROC has no PEND or unclosed in-stream data swallows JCL ([#59](https://github.com/Landparty/jcl-parser/issues/59)) ([f7436cb](https://github.com/Landparty/jcl-parser/commit/f7436cb2b62fc8fd877c289fc6d7d217a9a4050b))
* warn when a qualified DD override names no procedure step ([#64](https://github.com/Landparty/jcl-parser/issues/64)) ([1cc00c3](https://github.com/Landparty/jcl-parser/commit/1cc00c343db44d8d16f8e5b944e969cf4a8df91c))


### Documentation

* add codebase audit and prioritised refactor plan ([e5408e4](https://github.com/Landparty/jcl-parser/commit/e5408e47d04f65bedbaa41c0cbf528a87250b0f1))
* interface contract — parse_jcl never returns None, str is always content ([a61830a](https://github.com/Landparty/jcl-parser/commit/a61830acd57c87e90b33a6022f2b036cf72ae4ca))
* **okf:** audit bundle against current code ([d9c73d6](https://github.com/Landparty/jcl-parser/commit/d9c73d6c87ce5f3910f9fb240e645116dd6dadf9))
* **okf:** audit bundle against current code ([1918459](https://github.com/Landparty/jcl-parser/commit/1918459cc533c9d9aee167a55093a9a26d2d1480))
* **okf:** correct fabricated APIs and close the PR [#42](https://github.com/Landparty/jcl-parser/issues/42) gap in the bundle ([bebc7ba](https://github.com/Landparty/jcl-parser/commit/bebc7bab2796e3365f36b785521342d88179c95b))
* **okf:** format the validation_level example for ruff ([da7afe1](https://github.com/Landparty/jcl-parser/commit/da7afe1d8dc045905fe483ee9cbcb8339725a030))
* **okf:** record the 2026-09-28 bug-hunt fixes ([c535814](https://github.com/Landparty/jcl-parser/commit/c5358143b716c37647df5b15364206b077aabced))
* **okf:** separate the update-log entries with blank lines ([af1c077](https://github.com/Landparty/jcl-parser/commit/af1c077ff10c3c8ef36269c11034a86c1df8033b))

## [1.4.0](https://github.com/Landparty/jcl-parser/compare/v1.3.0...v1.4.0) (2026-09-01)


### Features

* publish jcl-parser to PyPI as closed-source compiled wheels ([54c0257](https://github.com/Landparty/jcl-parser/commit/54c0257c6a56121c269e693092986aac617b0e45))

## [1.3.0](https://github.com/Landparty/jcl-parser/compare/v1.2.1...v1.3.0) (2026-08-16)


### Features

* **program_profiles:** add profiles for the rest of the IBM utility catalogue ([c7cd0dc](https://github.com/Landparty/jcl-parser/commit/c7cd0dc9355777088d072edadb62ca1ca9535d11))


### Bug Fixes

* address Copilot review findings on ADRDSSU/IEBUPDTE/IRXJCL profiles ([4e53cf1](https://github.com/Landparty/jcl-parser/commit/4e53cf199833c72925622b5c76d1988fd4d11e00))

## [1.2.1](https://github.com/Landparty/jcl-parser/compare/v1.2.0...v1.2.1) (2026-08-16)


### Bug Fixes

* sync release-please package-name with pyproject.toml project name ([40aed62](https://github.com/Landparty/jcl-parser/commit/40aed62b84a8e1019dd657d5539656ce3ccda8ba))
* **workflow:** update job-level permissions for pypi publishing ([6c39f23](https://github.com/Landparty/jcl-parser/commit/6c39f231e2cc008d9553a52c560a8a3e684823ec))

## [1.2.0](https://github.com/Landparty/jcl-parser/compare/v1.1.0...v1.2.0) (2026-08-15)


### Features

* **logging:** add INFO/DEBUG diagnostics across the parse pipeline ([48c7f3f](https://github.com/Landparty/jcl-parser/commit/48c7f3ff7f54c08a9aadc383a23471405a526700))
* **workflow:** add manual dispatch for testpypi and pypi publishing ([8b1e878](https://github.com/Landparty/jcl-parser/commit/8b1e878412cc9c815de8813b744813bced7c4707))


### Bug Fixes

* address Copilot review findings on PR [#32](https://github.com/Landparty/jcl-parser/issues/32) ([cc5f8d7](https://github.com/Landparty/jcl-parser/commit/cc5f8d7876c4483527cb9a28fd5f6be1519de2c1))
* close remaining silent-drop findings from parser audit ([e74b57c](https://github.com/Landparty/jcl-parser/commit/e74b57c1f39e4216e58d6e23bf18ac5ed0066242))
* correct project name to "jcl-parser" in configuration files ([3775a2e](https://github.com/Landparty/jcl-parser/commit/3775a2e38895e4adeeb49ce80ef09db2ecdebdcc))
* eliminate silent data loss in parsing, continuation, and symbol resolution ([c5a5eed](https://github.com/Landparty/jcl-parser/commit/c5a5eed92e23361f43a039b3d9b4e54cf8804259))
* **parser:** resolve multiple silent data loss and dispatch bugs ([dc8024b](https://github.com/Landparty/jcl-parser/commit/dc8024b20e1ff5c4bb953f4cd2ea5a1187f3ee55))
* preserve && through SET-value resolution, not just DD substitution ([f73611c](https://github.com/Landparty/jcl-parser/commit/f73611ca8cb80d83db71e6b4c67bd00f1ecacf06))


### Documentation

* Add comprehensive documentation for CLI, API, data model, parsing pipeline, and development workflow ([2ed4fc9](https://github.com/Landparty/jcl-parser/commit/2ed4fc9e0812baf7a966eeb8f0099b4456842c9b))
* Add comprehensive documentation for CLI, public API, data model, parsing pipeline, and development workflow ([7836064](https://github.com/Landparty/jcl-parser/commit/7836064c7a19c6dc4e40dbac4adcf77924003573))
* add OKF docs, drift-prevention hooks, and homogenize README ([ab47105](https://github.com/Landparty/jcl-parser/commit/ab47105ffb29e7bd53571bbcae9ea4fcc91fbb3d))
* **changelog:** record removed APIs and correctness fixes ([039da89](https://github.com/Landparty/jcl-parser/commit/039da897ee1bf097cb3e555a20871e073e469323))
* Enhance documentation for DD overrides in PROC expansion and update log entries ([1cd6461](https://github.com/Landparty/jcl-parser/commit/1cd6461f3e0df6bef660594be6b148eba1a26f91))
* Initialize OKF knowledge bundle with core concepts, API, validation, and development workflow ([fcca35c](https://github.com/Landparty/jcl-parser/commit/fcca35c60d406a61d80f61bf9db4edf441e77764))
* **spec:** design for extended INFO/DEBUG parser logging ([68363c4](https://github.com/Landparty/jcl-parser/commit/68363c46998bef8c2f1861e1ae90465147d05f2e))
* Update citations in documentation files for consistency and accuracy ([0ea5edf](https://github.com/Landparty/jcl-parser/commit/0ea5edf5817d3093e7f3a2bcdffff9bfb38a09f2))
* Update CLI reference and usage details; correct parsing pipeline description; add diagnostic logging section ([117d43e](https://github.com/Landparty/jcl-parser/commit/117d43ef972692778a16669c8c9e6fa6312b7696))
* Update log and documentation for symbolic parameter substitution improvements ([d56c3ab](https://github.com/Landparty/jcl-parser/commit/d56c3ab2df72c86de17b013600268033aea85c15))

## [1.1.0](https://github.com/Landparty/jcl-parser/compare/v1.0.0...v1.1.0) (2026-06-25)


### Features

* add --profile CLI flags to expose parse profiling metrics ([fac1e63](https://github.com/Landparty/jcl-parser/commit/fac1e63ffc5dbed0814e6b3f0d79984942c66d45))
* add 'procs' CLI query for inspecting expanded PROC information ([bd7c680](https://github.com/Landparty/jcl-parser/commit/bd7c6800877020c7cc192522b3646a9b6c4e142c))
* add advanced configuration options for language servers and memory management ([ed93d3f](https://github.com/Landparty/jcl-parser/commit/ed93d3f91663fe98f20eeeffc2927e46de4583fe))
* Add CLAUDE.md for project guidance and command instructions ([d0f3f83](https://github.com/Landparty/jcl-parser/commit/d0f3f8374cf7ee442bdf44f4c33ebcfd79e5014b))
* add DFSRRC00 profile and corresponding tests for application program identification ([6fb394b](https://github.com/Landparty/jcl-parser/commit/6fb394bee85256cb2e058a4b21b966d5161b5994))
* add DictProcedureLoader to jclparser ([c921467](https://github.com/Landparty/jcl-parser/commit/c92146709f50705f6730e493cff24b38ffbd5eb2))
* Add DIVIDE.JCL example for dataset splitting and enhance continuation line handling ([ecc0d05](https://github.com/Landparty/jcl-parser/commit/ecc0d051283df0f9289a83d270a3f0685d2c30c4))
* Add initial LICENSE and constitution files for project guidelines and legal terms ([4478030](https://github.com/Landparty/jcl-parser/commit/44780301b606d70224786323beca32122e1484b5))
* add Playwright MCP YAML files to .gitignore ([2ed0307](https://github.com/Landparty/jcl-parser/commit/2ed0307bf80f6abedee93e497a0318f89dddb045))
* add profiling module with cProfile/tracemalloc/psutil support ([7428c5c](https://github.com/Landparty/jcl-parser/commit/7428c5c0be20452fb3f2b12fa2f33bb372e4364a))
* add profiling overloads to parse_jcl() with _parse_jcl_core() extraction ([7eef1cf](https://github.com/Landparty/jcl-parser/commit/7eef1cfc1fad195d6f5d26d7c100418712378286))
* add profiling support to parse_jcl() via enable_profiling param ([4f9c0be](https://github.com/Landparty/jcl-parser/commit/4f9c0be5925e4d1373d2100255db2764be54c04e))
* add setup.py for package configuration and mypyc integration ([87ec69e](https://github.com/Landparty/jcl-parser/commit/87ec69eb55944028b44da13dab55724474bf5d95))
* allow DD statements before EXEC and attach to first step ([c6a029d](https://github.com/Landparty/jcl-parser/commit/c6a029d0c29968307d19b339c24da56feae7d6bc))
* **cli:** add analyze subcommand ([223858a](https://github.com/Landparty/jcl-parser/commit/223858ac830434c46ac8996049685ae7ce4a08fc))
* **cli:** add datasets subcommand ([8f36345](https://github.com/Landparty/jcl-parser/commit/8f3634573a16e84961c282d833f57571d23bb659))
* **cli:** add detect subcommand ([9cd24f5](https://github.com/Landparty/jcl-parser/commit/9cd24f5c26f49553e6ff90abd93b0770d7b996a0))
* **cli:** add lint subcommand with --lint-list ([c783dbf](https://github.com/Landparty/jcl-parser/commit/c783dbfd690824ae5d7a4b9d1f39869d1608ade9))
* **cli:** add metrics subcommand ([21a979b](https://github.com/Landparty/jcl-parser/commit/21a979bbd56d52b3f7caae6e3d9e2b87bc85c305))
* **cli:** add paths subcommand ([07ec5fb](https://github.com/Landparty/jcl-parser/commit/07ec5fb9fa22043c0096caaa5b5bed2fda3b54d8))
* **cli:** add sql subcommand ([e56c001](https://github.com/Landparty/jcl-parser/commit/e56c0017702beccafc8f7ccac0b86f257a63f3e6))
* complete procs CLI feature with 5 improvements ([9f30a9d](https://github.com/Landparty/jcl-parser/commit/9f30a9d37729d615639b2bafb8c06a128aa07cd9))
* distinguish inline vs external PROCs in procs query output ([96db953](https://github.com/Landparty/jcl-parser/commit/96db953227c7560074c6aef7401ed0c40d7829de))
* Enhance continuation line handling with improved context awareness and additional detection logic ([55cc8df](https://github.com/Landparty/jcl-parser/commit/55cc8df60507df5d77733013282501634a6eb6a2))
* enhance JCL parser with external PROC loading support and add comprehensive tests ([253d345](https://github.com/Landparty/jcl-parser/commit/253d3456c6e3cc59f8cdd59c0de8c75f698c972f))
* export ProfilingResult and FunctionProfile from jclparser public API ([68ae1db](https://github.com/Landparty/jcl-parser/commit/68ae1db1d569ededb3d92745361a3912a0157dc1))
* Implement JCL parsing for conditional logic, PROC expansion, and various real-world JCL structures with comprehensive unit and integration tests. ([59527a5](https://github.com/Landparty/jcl-parser/commit/59527a567ff1a7342ca3739ed1fe8ba2c020dcda))
* implement six high-value parser features ([bbc31c5](https://github.com/Landparty/jcl-parser/commit/bbc31c599789ad43645edad0270c2cf630ef6bd5))
* introduce JCL parsing library with models, parser, validators, procedure loading, explosion logic, and comprehensive tests. ([abeac44](https://github.com/Landparty/jcl-parser/commit/abeac442fd2900c9b9099904fd6d3cab0f15073a))
* **parser:** implement SET symbol resolution and enhance parsing logic ([5f6dcb0](https://github.com/Landparty/jcl-parser/commit/5f6dcb020be73b4b58c593c5dcfab65ea7596f7b))
* **parser:** implement SET symbol resolution for DD dataset names ([bb9bece](https://github.com/Landparty/jcl-parser/commit/bb9bece9ad4f444178a17f386928eb7d114c34fc))
* **parser:** optimize DDStatement and Step cloning for performance ([d19a097](https://github.com/Landparty/jcl-parser/commit/d19a0973d77299e19db939f831452c98bc10db17))
* **program-profiles:** surface programs invoked via SYSTSIN/SYSIN ([0ae7b5f](https://github.com/Landparty/jcl-parser/commit/0ae7b5fc802ccfc7526f773e37b74c3b55963b5f))
* raise JCLStructureError in strict mode for DD before EXEC ([8baf5e4](https://github.com/Landparty/jcl-parser/commit/8baf5e49dd7f5ebd8c81deff8dfce8cd28d7c6f6))
* **tests:** add comprehensive tests for JCL parsing edge cases and examples ([8410b1e](https://github.com/Landparty/jcl-parser/commit/8410b1eb049543e884f48fb5012eb8fb29b6ad02))


### Bug Fixes

* **_invoked:** resolve CALL operand before scanning for a member ([346bd69](https://github.com/Landparty/jcl-parser/commit/346bd69051ef376494d4049697ec4e1079e0c4b9))
* address all 20 PR review comments — strengthen assertions and use public API ([217c4c2](https://github.com/Landparty/jcl-parser/commit/217c4c2abf2e753c1cb3454af1dea0d072e96a36))
* address all PR review comments ([b76d82b](https://github.com/Landparty/jcl-parser/commit/b76d82bd1548e94ca3a301825d228dcd08eea0a9))
* address PR review comments from Copilot ([2516ad5](https://github.com/Landparty/jcl-parser/commit/2516ad566acec5ab16cebb5dc73319b6b0bfbd51))
* address PR review comments on test accuracy ([fec7d2a](https://github.com/Landparty/jcl-parser/commit/fec7d2a7ddae969d2e18a2425804bf539fda47e7))
* address PR review issues ([f9590dc](https://github.com/Landparty/jcl-parser/commit/f9590dc250d84cf28b7b8151115cf873bd7e9efb))
* close three remaining edge-case gaps found in completeness audit ([76809d7](https://github.com/Landparty/jcl-parser/commit/76809d77c18bae9f1bbd1809988f43d0de79344e))
* correct content variable shadowing and add lenient-mode test for JCLStructureError ([709855a](https://github.com/Landparty/jcl-parser/commit/709855a587d2130284622ca6cf1f7fcf66c5786d))
* guard ConditionalBlock access and allow EXEC inside PROC definitions ([484acd1](https://github.com/Landparty/jcl-parser/commit/484acd14bed216db239add089e20f914833da218))
* improve unmatched parentheses error message and enhance normalization logic for JCL lines ([fe355a9](https://github.com/Landparty/jcl-parser/commit/fe355a945369aa06c8e1231838ad8501146f80c1))
* project audit — consolidate config, add CI, fix lint, model OUTPUT statements ([0e6f0e4](https://github.com/Landparty/jcl-parser/commit/0e6f0e422b6bede8fc814866dd514041bf3cc28f))
* Python 3.10 compatibility — add future annotations and tomli fallback ([46498b0](https://github.com/Landparty/jcl-parser/commit/46498b0b6b0bd3553b032503c4b2ce80901f8e1b))
* z/OS-accurate DD * in-stream data termination ([ded9cfb](https://github.com/Landparty/jcl-parser/commit/ded9cfb7b8a188195c0bcce1f0892e7314dd78f8))


### Performance Improvements

* add benchmark fixtures for three algorithmic hot paths ([86cbae4](https://github.com/Landparty/jcl-parser/commit/86cbae49197158d676e453a5bf032e9879ab36c6))
* cache continuation context incrementally instead of full rescan ([709e9c1](https://github.com/Landparty/jcl-parser/commit/709e9c1f452035393a8a61fcc4791a57ff1d51ba))
* collapse 3-pass inline data detection into single pass ([0c5aff2](https://github.com/Landparty/jcl-parser/commit/0c5aff27847f9de45198dbb70f79f214391feb14))
* replace character-list joins with index slicing in parameter parsers ([957b5dc](https://github.com/Landparty/jcl-parser/commit/957b5dc9db71688f26f70f7fab137553bf618513))


### Documentation

* add algorithmic performance fixes design spec ([c8b792c](https://github.com/Landparty/jcl-parser/commit/c8b792ce80bdfafc26122413da3d87c48b75f54b))
* add CLI completion design spec ([68fee10](https://github.com/Landparty/jcl-parser/commit/68fee1021604f701cc452957f2bfd7ca0ec15b7d))
* add CLI completion implementation plan ([9d866d5](https://github.com/Landparty/jcl-parser/commit/9d866d5549dbb463da737cb9083b8411a4f37206))
* add documentation audit design spec ([5de20ab](https://github.com/Landparty/jcl-parser/commit/5de20abc7162a8bc731dcad7bdf74546159a5350))
* add implementation plan for algorithmic performance fixes ([573139d](https://github.com/Landparty/jcl-parser/commit/573139dbe44f1b0dcbdbf2221178f01258e4f9e4))
* add performance profiling design spec ([b0b01d3](https://github.com/Landparty/jcl-parser/commit/b0b01d395a96fa3cc4ed18156e0ff257997e68b7))
* add performance profiling implementation plan ([a40da4f](https://github.com/Landparty/jcl-parser/commit/a40da4f1e420d8af7655eed46dbc5b78422af576))
* **cli:** update module docstring with all 7 new subcommands ([2996123](https://github.com/Landparty/jcl-parser/commit/299612319f2a3f469043594936fb78a2fcf4f193))
* rewrite README as concise index; add four example guides under docs/ ([ae4768d](https://github.com/Landparty/jcl-parser/commit/ae4768d35eda8cdaa317f1566be63bdbdd415d6a))
* update CLAUDE.md and README.md for improved clarity and accuracy ([973ee8d](https://github.com/Landparty/jcl-parser/commit/973ee8d8de1b0e5ffbdf4b79df7d9d2cc9243d0a))
* update CLAUDE.md with project overview, backend integration, test structure, and code style guidelines ([c778c6e](https://github.com/Landparty/jcl-parser/commit/c778c6e0d14a32da3afedd315646625b1a908aaa))

## [Unreleased]

### Changed

- In-stream data opened with `DD *` (and no explicit `DLM=`) is now terminated
  by the next record beginning with `//`, matching z/OS. Previously such data
  was collected until `/*` or end-of-file, which could silently swallow the
  following JCL statement. `DD DATA` is unchanged: `//` records remain part of
  the data and only `/*` (or a custom `DLM=`) ends it. A missing `/*` is no
  longer treated as a validation error — the next statement, or end-of-file,
  legitimately closes the data.

### Fixed

- In-stream data that runs to end-of-file without a closing delimiter is no
  longer silently discarded; the collected records are now attached to the DD
  statement's `inline_data`.
- `explode_job` now threads the JCLLIB ORDER as an immutable tuple through every
  nesting level, honoring the loaders' hashable-key contract. Added regression
  tests covering nested PROC resolution across multiple libraries (including
  library-order precedence and inline-to-external nesting).
- SQL/DB2 detection now recognises `IKJEFT1A` (it was already handled by the
  IKJEFT01 program profile but missing from `sql_detector.DB2_PROGRAMS`, so a
  job running it was profiled as DB2 yet skipped by SQL detection).
- `explode_job(strict_symbols=True)` now also raises `UndefinedSymbolError` for
  undefined `&SYMBOL` references inside expanded PROC bodies. Previously strict
  mode only applied to non-PROC steps and silently dropped undefined symbols in
  PROC expansion. Added a regression test.

### Removed

These symbols were unused internal/compatibility surface (not part of a tagged
release) and have been removed along with their tests:

- **`ParameterValidator`** and its `validate_*` methods (the parameter
  validator pack added earlier in this unreleased cycle). The class was never
  wired into `validate_jcl()` and had no callers outside its own tests. The
  live `DISPValidator` / `DatasetNameValidator` are unaffected.
- Deprecated/orphaned `jclparser.utils` helpers that were no longer on the
  parse path and had no in-package callers: `split_jcl_parameters`,
  `parse_jcl_parameter`, `quote_jcl_value`, `unquote_jcl_value`,
  `validate_jcl_name` (use `validators.validate_jcl_identifier`),
  `format_jcl_line`, `extract_inline_data`, `calculate_jcl_checksum`,
  `is_continuation_line` (use `ContinuationLineHandler.is_continuation_line`),
  and the module-level `merge_continuation_lines` wrapper (use
  `ContinuationLineHandler().merge_continuation_lines`).
- Other dead code: `validators.validate_parameter_syntax`, the non-functional
  `JobMetrics.metrics` back-compat field, `JESControlStatement.to_source`,
  `program_profiles.clear_profiles`, and the never-instantiated
  `parameter_ast.SimpleParameter` / `ListParameter` nodes.

## [1.0.0] - 2026-03-31

First stable release.

### Added

**Core parsing**
- `parse_jcl()` — parses JOB, EXEC, DD, PROC/PEND, SET, IF/THEN/ELSE/ENDIF, JCLLIB ORDER statements from string, `Path`, or file-like object
- `validate_jcl()` — non-raising validation returning a list of `ParseError` objects
- `parse_statement()` — parse a single JCL line into a `Statement`
- Full continuation-line support (column-71 breaks, multi-line parameters, nested parentheses across lines)
- Inline data (`DD *`, `DD DATA`, custom `DLM=` delimiters)
- JES2/JES3 control statements (`/*JOBPARM`, `/*ROUTE`, etc.) captured in `job.jes_statements`
- GDG relative generation references (`MY.GDG(+1)`, `MY.GDG(-1)`, `MY.GDG(0)`)
- Symbol substitution (`&SYMBOL`, `&&` escape, trailing-period disambiguation)

**PROC expansion**
- `explode_job()` — expands inline and external PROC calls, resolves symbolic parameters
- External PROC loading via `JCLLIB ORDER`; filesystem layout mirrors mainframe dataset naming
- `JCL_PROCLIB_PATH` environment variable as a default proc base path
- `CircularProcedureError` on cyclic PROC references
- `ProcedureNotFoundError` when a referenced PROC cannot be resolved

**Validation & error hierarchy**
- `JCLSyntaxError` — malformed syntax (unclosed quotes, unmatched parentheses, …)
- `JCLValidationError` — semantic violations
- `JCLStructureError` — structural violations (e.g. DD before any EXEC in strict mode)
- `strict_mode=True` on `parse_jcl()` promotes validation issues to exceptions

**Structured parameters**
- DCB subparameters exposed as typed `DCBParameter` object (`recfm`, `lrecl`, `blksize`, …)
- SPACE parameters exposed as typed `SPACEParameter` object (`unit`, `primary`, `secondary`, `rlse`, …)
- `_parse_parameters` delegates comma-splitting to the canonical `ParameterParser` implementation

**Additional modules**
- `condition_parser` — parses `// IF` expressions into a typed AST (`AndCondition`, `OrCondition`, `ReturnCodeCondition`, `AbendCondition`, …)
- `sql_detector` — detects SQL/DB2 program usage in steps (`detect_sql_in_step`, `detect_sql_in_job`)
- `jcl_file_type` — heuristic detection of JCL vs PROC files (`detect_file_type`, `is_jcl_file`, `is_proc_file`)
- `system_symbols` — pluggable JCL system symbol provider (`&SYSUID`, `&SYSDATE`, …)

**Plugin system**
- `StatementPlugin` — register custom statement parsers
- `ValidationPlugin` — register custom validation rules
- `PluginRegistry` / `get_plugin_registry()` — global plugin registry
- `ParserConfig` — per-parse configuration (dialect, validation level, plugin list)

**Developer experience**
- Multi-encoding file reading (utf-8 → latin-1 → cp1252 → binary fallback)
- 1 218 tests, 92 % branch coverage (minimum enforced at 90 %)
- Four example guides under `docs/`
- Full fixture catalogue in `tests/fixtures/sample_jcl/README.md`

### Changed

- `pyproject.toml` classifier updated from *Alpha* to *Production/Stable*
- Dead lazy-import machinery (`_LAZY` / `__getattr__`) removed from `__init__.py`
- Deprecated `utils.merge_continuation_lines` now delegates to `ContinuationLineHandler` instead of re-implementing the algorithm
- File-reading logic consolidated into `utils._read_file_with_fallback`

### Fixed

- Variable shadowing in JES-statement branch of `parse_jcl` that prevented `JCLStructureError` from firing correctly in strict mode
- Unmatched-parentheses error message now includes a column-71 continuation hint

---

## [0.1.0] - 2025-01-20

Initial release — core parsing of JOB, EXEC, and DD statements; basic PROC support; plugin skeleton; Python 3.13+.
