# Changelog

All notable changes to this project will be documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.3.3](https://github.com/Landparty/jcl-parser/compare/v2.3.2...v2.3.3) (2026-11-14)


### Bug Fixes

* **profiles:** read IBM's INITT statements in the IEHINITT profile ([#206](https://github.com/Landparty/jcl-parser/issues/206)) ([8967451](https://github.com/Landparty/jcl-parser/commit/89674519ac032efc2fe751f7c31c4c0c9f370f77))
* TSO SQL with unread SYSTSIN, IMS region program, labelled utility statements ([b407c92](https://github.com/Landparty/jcl-parser/commit/b407c92207d55b7e6c9c45cc581e3d11d3b2a364))

## [2.3.2](https://github.com/Landparty/jcl-parser/compare/v2.3.1...v2.3.2) (2026-11-13)


### Bug Fixes

* bugs from the 2026-11-10 bug hunts (passes 1-2, all-samples run) ([90e9af4](https://github.com/Landparty/jcl-parser/commit/90e9af4be6c3b6fee48b40c409050d605860b9a0))
* bugs from the 2026-11-10 bug hunts (passes 1-2, all-samples run) ([86e0b8d](https://github.com/Landparty/jcl-parser/commit/86e0b8d34fce83622ba06628cbb92d9b9efae1f3))
* bugs from the 2026-11-10/11 bug hunts (passes 3-21) ([ecca147](https://github.com/Landparty/jcl-parser/commit/ecca147645773ee92c393d9bc5ef713b10ca6ea4))
* compare temporary dataset names case-insensitively ([44824b5](https://github.com/Landparty/jcl-parser/commit/44824b51137a3fab79dbcc9d4a06242116355b09))
* datasets a called PROC creates exist for later job steps ([de39490](https://github.com/Landparty/jcl-parser/commit/de39490afad68b6167bad40b7dcd0a28ea1f4ee1))
* delete-and-recreate lineage, nameless PROC members, JES3 continuations, VOL=SER opens ([#187](https://github.com/Landparty/jcl-parser/issues/187)) ([6757711](https://github.com/Landparty/jcl-parser/commit/675771131323be97eea6a3c8382ec1a12ee9db08))
* don't re-scan quoted values for symbol operands ([068193b](https://github.com/Landparty/jcl-parser/commit/068193ba7067b3504939b80e4b79db86835889a3))
* lineage PROC recreate, JES quoted commas, use after DELETE, INCLUDE line refs, in-stream SET values ([e85d0dd](https://github.com/Landparty/jcl-parser/commit/e85d0dd29362d8af2af5b6cb7321ccf7306dad50))
* lineage PROC recreate, JES quoted commas, use after DELETE, INCLUDE line refs, in-stream SET values ([2438947](https://github.com/Landparty/jcl-parser/commit/24389470689d2e6629fbffa7d9485435e85bdff3)), closes [#189](https://github.com/Landparty/jcl-parser/issues/189) [#190](https://github.com/Landparty/jcl-parser/issues/190) [#191](https://github.com/Landparty/jcl-parser/issues/191) [#194](https://github.com/Landparty/jcl-parser/issues/194) [#197](https://github.com/Landparty/jcl-parser/issues/197)
* problems found by running every CLI subcommand on open-source JCL ([6b412a1](https://github.com/Landparty/jcl-parser/commit/6b412a13f11eaddd77f405f8f0a823b8e8e61b15))

## [2.3.1](https://github.com/Landparty/jcl-parser/compare/v2.3.0...v2.3.1) (2026-11-06)


### Bug Fixes

* deleting job runs after every reader; continued SET feeds INCLUDE member ([2c649cc](https://github.com/Landparty/jcl-parser/commit/2c649ccb8eba9983ea1f12858d358285dcc5c106))
* deleting job runs after every reader; continued SET feeds INCLUDE member ([a4be590](https://github.com/Landparty/jcl-parser/commit/a4be5903e1b0cda0424a5fb1fa38bbcb76272ffa)), closes [#179](https://github.com/Landparty/jcl-parser/issues/179) [#180](https://github.com/Landparty/jcl-parser/issues/180)

## [2.3.0](https://github.com/Landparty/jcl-parser/compare/v2.2.3...v2.3.0) (2026-11-05)


### Features

* **cli:** friendlier jcl-parser help, --format alias and did-you-mean hints ([283925b](https://github.com/Landparty/jcl-parser/commit/283925be64c9759d15b03b2427bd6ea4cddd9bd2))
* **cli:** friendlier jcl-parser help, --format alias and did-you-mean hints ([55d39da](https://github.com/Landparty/jcl-parser/commit/55d39daf62e2743a05380172ef717ebd0e89e2d1))


### Bug Fixes

* report PROC symbolics the PROC never uses (IEFC657I); IMS MSG regions name no program ([84de84b](https://github.com/Landparty/jcl-parser/commit/84de84b25826a479e36c8b947f9d0afc17b36ae8))
* report PROC symbolics the PROC never uses (IEFC657I); IMS MSG regions name no program ([6454fb3](https://github.com/Landparty/jcl-parser/commit/6454fb311f9b74b6982e1a0e9c3ea75d0f750883))
* symbolics used only in a PROC call's override DDs are not IEFC657I ([cad1a38](https://github.com/Landparty/jcl-parser/commit/cad1a386b5745dcd30b476c6c2d49944f01debfb))
* symbolics used only in a PROC call's override DDs are not IEFC657I ([096a084](https://github.com/Landparty/jcl-parser/commit/096a0840fda592204bd2c2d8f1624e19f8c69b2b)), closes [#176](https://github.com/Landparty/jcl-parser/issues/176)

## [2.2.3](https://github.com/Landparty/jcl-parser/compare/v2.2.2...v2.2.3) (2026-11-03)


### Bug Fixes

* name a DD concatenation member by its owning DD in lint and validation messages ([#170](https://github.com/Landparty/jcl-parser/issues/170)) ([9dfdc4c](https://github.com/Landparty/jcl-parser/commit/9dfdc4c0671f1f4f7ae20c874c630734f10f44d1)), closes [#169](https://github.com/Landparty/jcl-parser/issues/169)

## [2.2.2](https://github.com/Landparty/jcl-parser/compare/v2.2.1...v2.2.2) (2026-11-02)


### Bug Fixes

* **lifecycle:** name the owning DD for a concatenation member ([#166](https://github.com/Landparty/jcl-parser/issues/166)) ([#167](https://github.com/Landparty/jcl-parser/issues/167)) ([93ca7b3](https://github.com/Landparty/jcl-parser/commit/93ca7b32711104050b42029d411d8206dcf3e330))

## [2.2.1](https://github.com/Landparty/jcl-parser/compare/v2.2.0...v2.2.1) (2026-11-02)


### Bug Fixes

* a //*DATASET comment without DDNAME= is a comment ([#164](https://github.com/Landparty/jcl-parser/issues/164)) ([f9b42e6](https://github.com/Landparty/jcl-parser/commit/f9b42e6a1e84f1b1cdb03907677c1d339fa9b527))
* a //*DATASET comment without DDNAME= is a comment ([#164](https://github.com/Landparty/jcl-parser/issues/164)) ([3036331](https://github.com/Landparty/jcl-parser/commit/3036331ce492e40c49835bbd58c064f0cfa4e1e0))
* **explosion:** expand INCLUDEs inside a cataloged PROC ([1e2dce4](https://github.com/Landparty/jcl-parser/commit/1e2dce4560685fd9b411f128cfbcc0fad2ab8c0d)), closes [#153](https://github.com/Landparty/jcl-parser/issues/153)
* INCLUDE MEMBER=&symbol in a cataloged PROC; BPXBATCH STDPARM ([088ce06](https://github.com/Landparty/jcl-parser/commit/088ce0622e36b828ff0abe79a025c3dbd56f0a76)), closes [#160](https://github.com/Landparty/jcl-parser/issues/160) [#159](https://github.com/Landparty/jcl-parser/issues/159)
* JES3 //*DATASET records are the data set's content, not SYSIN or JCL ([f3f821d](https://github.com/Landparty/jcl-parser/commit/f3f821da8ec3625a41b868f4d50e7d045d7b57eb))
* **lineage:** a PROC member without a PROC statement explodes its callers ([a8f4dae](https://github.com/Landparty/jcl-parser/commit/a8f4dae182924992461797cbbf52c85a6134fb3f)), closes [#147](https://github.com/Landparty/jcl-parser/issues/147)
* **lint:** lint PROC members and in-stream PROC bodies ([b167395](https://github.com/Landparty/jcl-parser/commit/b16739561ac0cdfa4c0d25e9d0d94f1aac7498ae)), closes [#149](https://github.com/Landparty/jcl-parser/issues/149)
* **lint:** suppression codes may have blanks after commas; in-stream data is not a directive ([c45fbbb](https://github.com/Landparty/jcl-parser/commit/c45fbbb75b6f6eb2ad68a52e67b4589384b261e2)), closes [#150](https://github.com/Landparty/jcl-parser/issues/150)
* **profiles:** DSNUTILB splits SYSIN into whole utility statements ([1c26d94](https://github.com/Landparty/jcl-parser/commit/1c26d94314f5715dda9bed4de61b76bfe813a649)), closes [#156](https://github.com/Landparty/jcl-parser/issues/156)
* **profiles:** ICETOOL knows DATASORT and SUBSET, notes DISCARD/WRITE/LIST outputs ([553d265](https://github.com/Landparty/jcl-parser/commit/553d26514bce03a616ecf7c4eed488fea35bf13e)), closes [#154](https://github.com/Landparty/jcl-parser/issues/154)
* the six open issues (cataloged-PROC INCLUDE, PROC lint, bare PROC members, suppressions, ICETOOL, DSNUTILB) ([b7cdecd](https://github.com/Landparty/jcl-parser/commit/b7cdecdd3d00903e53afbb56208bec0894b3187c))

## [2.2.0](https://github.com/Landparty/jcl-parser/compare/v2.1.0...v2.2.0) (2026-10-30)


### Features

* **lineage:** cross-job dataset lineage for a directory of jobs ([8963c17](https://github.com/Landparty/jcl-parser/commit/8963c17f55cc8d2475c766ecd75d5f8c25d57edd))
* **lint:** lint in CI: jcl-lint, directory lint/validate, SARIF, config, suppressions ([83b499f](https://github.com/Landparty/jcl-parser/commit/83b499f23c984b7162b5915c87fdfb75862c4858))
* public JSON export and cross-job dataset lineage ([91c1fbb](https://github.com/Landparty/jcl-parser/commit/91c1fbb4b4cb8d7bca792bf444d1c457e3dfa3d2))
* **serialization:** public JSON export with a versioned JSON Schema ([bbad952](https://github.com/Landparty/jcl-parser/commit/bbad952f66a5982b289ad8f6c44c635e9833406c))


### Bug Fixes

* **cli:** stdin as '-', --profile in every view, step and DD names win over query words ([88bc37b](https://github.com/Landparty/jcl-parser/commit/88bc37be5d49564458afd2babc302b30c9364453)), closes [#131](https://github.com/Landparty/jcl-parser/issues/131) [#132](https://github.com/Landparty/jcl-parser/issues/132) [#133](https://github.com/Landparty/jcl-parser/issues/133)
* **continuation:** a column-72 comment continuation is not a missing comma ([8fdfd7e](https://github.com/Landparty/jcl-parser/commit/8fdfd7e929c94cf26233b54be52a59a918d18766))
* **errors:** make library exceptions picklable and deep-copyable ([a6a414d](https://github.com/Landparty/jcl-parser/commit/a6a414d7238e2f8b722dbc3704294e48e39eeab7)), closes [#104](https://github.com/Landparty/jcl-parser/issues/104)
* **explosion:** qualify procedure step names in an expanded IF's condition text ([645eb18](https://github.com/Landparty/jcl-parser/commit/645eb184d9a7691a3f813eb17e88a724ed46e3af))
* land three bug-hunt carry-over fixes (comment continuation, IEFBR14, IEHLIST) ([68c2595](https://github.com/Landparty/jcl-parser/commit/68c2595c2787ef3bd80399a8133dcbecd7631a00))
* **lineage:** a DELETE disposition is not a write ([99a19b6](https://github.com/Landparty/jcl-parser/commit/99a19b69e815110c22fe394bb2791a25d9cfa9cf))
* **lineage:** use directory PROC members and match PDS members individually ([ec712bd](https://github.com/Landparty/jcl-parser/commit/ec712bd2ac06dca5a2bfa21d038f594c97275622)), closes [#144](https://github.com/Landparty/jcl-parser/issues/144) [#145](https://github.com/Landparty/jcl-parser/issues/145)
* **lint:** drop the DTZ005 noqa markers ruff 0.17.3 reports as unused ([f462331](https://github.com/Landparty/jcl-parser/commit/f4623317cd71e43fa92de31d2be706ea96421fc4))
* **model:** an omitted DISP defines a new dataset; annotate disposition as str | list[str] ([38fc5e3](https://github.com/Landparty/jcl-parser/commit/38fc5e3ae12335018ee9bd6252d53b4a04397802)), closes [#105](https://github.com/Landparty/jcl-parser/issues/105) [#97](https://github.com/Landparty/jcl-parser/issues/97)
* **parser:** end the job at a null statement, decode binary sources, read a Path once ([3baeac5](https://github.com/Landparty/jcl-parser/commit/3baeac5ccb99065784cec1a21e584416180d34ba)), closes [#124](https://github.com/Landparty/jcl-parser/issues/124) [#125](https://github.com/Landparty/jcl-parser/issues/125)
* **profiles:** count binder INCLUDE members, join IEHPROGM continuations, LINT-002 UNIT lists ([5624049](https://github.com/Landparty/jcl-parser/commit/5624049b655527c0515031eb5cab411826d9a64d)), closes [#112](https://github.com/Landparty/jcl-parser/issues/112) [#113](https://github.com/Landparty/jcl-parser/issues/113) [#114](https://github.com/Landparty/jcl-parser/issues/114)
* **profiles:** join ADRDSSU continuations before reading commands ([421ceeb](https://github.com/Landparty/jcl-parser/commit/421ceeb2fb098d22ebe629cb7c777a87c55fb643))
* **profiles:** note IEFBR14 DISP=(MOD,DELETE) as a delete ([0dcd069](https://github.com/Landparty/jcl-parser/commit/0dcd06966e4717e292305bd11983b18b3266a3ea))
* **profiles:** read IEHLIST statements with the control-statement tokeniser ([030cabb](https://github.com/Landparty/jcl-parser/commit/030cabb3ab67f85604bb76b6e9657a8d6940df85))
* **validation:** report unbalanced IF/ELSE/ENDIF and dangling backward references ([84e5c7d](https://github.com/Landparty/jcl-parser/commit/84e5c7d95e4c811879c4d8af0ea194a678a2eceb))
* **validation:** report unbalanced IF/ELSE/ENDIF and dangling backward references ([fab0007](https://github.com/Landparty/jcl-parser/commit/fab0007f83884b428ef4694efbd2851de6bb34ed))

## [2.1.0](https://github.com/Landparty/jcl-parser/compare/v2.0.3...v2.1.0) (2026-10-15)


### Features

* **model:** keep plugin statements of custom types in Job.custom_statements ([13540e4](https://github.com/Landparty/jcl-parser/commit/13540e487dc8a600f64395e356e5eb16e199b2cc)), closes [#130](https://github.com/Landparty/jcl-parser/issues/130)


### Bug Fixes

* address all severity:medium issues ([41aea41](https://github.com/Landparty/jcl-parser/commit/41aea41c4e012e654e5dd733b7180a03c017aac7))
* address review of the severity:high fixes ([9ce5359](https://github.com/Landparty/jcl-parser/commit/9ce5359d765cd67efe312c92581964f804688d3a)), closes [#94](https://github.com/Landparty/jcl-parser/issues/94)
* **cli:** honour --proc-path in --validate via validate_jcl keywords ([021e992](https://github.com/Landparty/jcl-parser/commit/021e9927dfffcc81cfcd7328de24cf070b8baec2)), closes [#129](https://github.com/Landparty/jcl-parser/issues/129)
* **condition:** evaluate AND and OR at the same precedence, left to right ([0cf1874](https://github.com/Landparty/jcl-parser/commit/0cf1874486e8f2add618604976be70c5923c66f5)), closes [#101](https://github.com/Landparty/jcl-parser/issues/101)
* **continuation:** only continue a statement after a trailing comma ([96f17be](https://github.com/Landparty/jcl-parser/commit/96f17be846a783cf17f8aad2c53afd51efc11c48)), closes [#123](https://github.com/Landparty/jcl-parser/issues/123)
* **continuation:** stop treating a backslash before a quote as an escape ([fae9920](https://github.com/Landparty/jcl-parser/commit/fae992087977b45453f58b0c4e94e022bc200e3e)), closes [#122](https://github.com/Landparty/jcl-parser/issues/122)
* **explosion:** collapse && from symbol values in PROC steps ([9ef6633](https://github.com/Landparty/jcl-parser/commit/9ef66335e1089132775d35bdecd8dfcfc44b0efd)), closes [#127](https://github.com/Landparty/jcl-parser/issues/127)
* **explosion:** resolve PROC-call overrides in the called PROC's scope ([d9601dc](https://github.com/Landparty/jcl-parser/commit/d9601dcd919faa87c6fbfb342cc9d3b842f8d44c)), closes [#126](https://github.com/Landparty/jcl-parser/issues/126)
* **include:** report line numbers after an INCLUDE against the main source ([72b5698](https://github.com/Landparty/jcl-parser/commit/72b5698ba229cf051d248ff8ca45700fca941c3d)), closes [#118](https://github.com/Landparty/jcl-parser/issues/118)
* **lifecycle:** treat a step that COND= can bypass as a conditional branch ([6fbcfec](https://github.com/Landparty/jcl-parser/commit/6fbcfec93811478ab83f204a5423365d5f3b19a1)), closes [#108](https://github.com/Landparty/jcl-parser/issues/108)
* **parser:** close IF blocks left open in an in-stream PROC at PEND ([1695a62](https://github.com/Landparty/jcl-parser/commit/1695a62eaf0d60482ff5a6115af629183cd16c17)), closes [#102](https://github.com/Landparty/jcl-parser/issues/102)
* **parser:** honour XMIT DLM= and skip JES2 /*XMIT transmitted data ([d3ee2bb](https://github.com/Landparty/jcl-parser/commit/d3ee2bb5e99e47b0a3f1c31396b0c27f27bdddf8)), closes [#117](https://github.com/Landparty/jcl-parser/issues/117)
* **parser:** keep a parenthesised DSN as text instead of crashing ([26b0d6a](https://github.com/Landparty/jcl-parser/commit/26b0d6ae7478a618892b3513b1b90fe08fd6d6d0)), closes [#121](https://github.com/Landparty/jcl-parser/issues/121)
* **parser:** keep columns 72-80 and tabs of in-stream data records ([8b4a08b](https://github.com/Landparty/jcl-parser/commit/8b4a08b9b3e2228c48b50df777f2b8bd925a3692)), closes [#115](https://github.com/Landparty/jcl-parser/issues/115)
* **parser:** keep job-level DDs out of in-stream PROC definitions ([fc04d7e](https://github.com/Landparty/jcl-parser/commit/fc04d7e91ce375f9b8cf38a4c9235d427308b069)), closes [#103](https://github.com/Landparty/jcl-parser/issues/103)
* **parser:** resolve SET symbols in JCLLIB ORDER library names ([c4deeb2](https://github.com/Landparty/jcl-parser/commit/c4deeb24f31d705cca56f6e26f607c48587fd3d3)), closes [#128](https://github.com/Landparty/jcl-parser/issues/128)
* **parser:** treat a quoted or parenthesised comment after a comma as a comment ([360769a](https://github.com/Landparty/jcl-parser/commit/360769a4cc2b754bb20383b53a07993c290dc147)), closes [#120](https://github.com/Landparty/jcl-parser/issues/120)
* **proc:** search builtins and SYS1.PROCLIB without a JCLLIB ([bba44b2](https://github.com/Landparty/jcl-parser/commit/bba44b2e5bbc60ee06ffe6ab811a9c2ec8e4e438)), closes [#116](https://github.com/Landparty/jcl-parser/issues/116)
* **profiles:** read batch FTP commands from the INPUT DD ([4c2e54d](https://github.com/Landparty/jcl-parser/commit/4c2e54d4c587280b262eb24dba69e673d5779850)), closes [#111](https://github.com/Landparty/jcl-parser/issues/111)
* **profiles:** report SORT OUTFIL and JOINKEYS datasets ([6de1aee](https://github.com/Landparty/jcl-parser/commit/6de1aeeb6abcd5653d4c41dd2c617814799616d6)), closes [#110](https://github.com/Landparty/jcl-parser/issues/110)
* **rc-analysis:** report a repeated nested IF only when nothing can change it ([254631b](https://github.com/Landparty/jcl-parser/commit/254631ba42795aef3135285013db6d2bfea9c682)), closes [#109](https://github.com/Landparty/jcl-parser/issues/109)
* resolve all severity:high issues ([#98](https://github.com/Landparty/jcl-parser/issues/98) [#99](https://github.com/Landparty/jcl-parser/issues/99) [#106](https://github.com/Landparty/jcl-parser/issues/106) [#107](https://github.com/Landparty/jcl-parser/issues/107) [#115](https://github.com/Landparty/jcl-parser/issues/115) [#116](https://github.com/Landparty/jcl-parser/issues/116) [#126](https://github.com/Landparty/jcl-parser/issues/126)) ([9d026fe](https://github.com/Landparty/jcl-parser/commit/9d026fed168e005088db32ee383b4d76fdc34de5))
* **sql,lint,metrics:** see DSNUPROC as DSNUTILB and PROC-call override DDs on unexploded jobs ([75e14fd](https://github.com/Landparty/jcl-parser/commit/75e14fd16208d1de165f0a37478865cfa6d16d82)), closes [#106](https://github.com/Landparty/jcl-parser/issues/106) [#107](https://github.com/Landparty/jcl-parser/issues/107)
* **validation:** accept JOB-less cataloged PROC members ([f1e9068](https://github.com/Landparty/jcl-parser/commit/f1e9068175183c16f544309fe8dd0bcbda219236)), closes [#98](https://github.com/Landparty/jcl-parser/issues/98)
* **validators:** let a JOB wrapping only in-stream PROCs validate clean ([d54726a](https://github.com/Landparty/jcl-parser/commit/d54726a04bbb15c003bc6857ddb24b457017f50c)), closes [#100](https://github.com/Landparty/jcl-parser/issues/100)
* **validators:** report step, DD and job findings at their source line ([6fe2c3b](https://github.com/Landparty/jcl-parser/commit/6fe2c3bcd258f60569d9cdeb913fab33303ade55)), closes [#119](https://github.com/Landparty/jcl-parser/issues/119)


### Documentation

* **contract:** job.steps is list[Step | ConditionalBlock]; export iter_execution_steps ([849cdeb](https://github.com/Landparty/jcl-parser/commit/849cdebdc5ca47f01e6cd3e1ef888b2d0061eace)), closes [#99](https://github.com/Landparty/jcl-parser/issues/99)
* **okf:** correct pipeline stage order and model/contract field types ([8ab2d05](https://github.com/Landparty/jcl-parser/commit/8ab2d05863fec4528588e43760db3cab9b623a10))
* **okf:** fix stale validate_jcl/parse_statement signatures and CLI details ([62ecb49](https://github.com/Landparty/jcl-parser/commit/62ecb4929bf96589f8685332b984927ff06bb7fb))
* **okf:** fix validation/PROC-expansion pages and log the audit ([165997f](https://github.com/Landparty/jcl-parser/commit/165997f85aebf967a4667e88a52b91f5632ed570))
* **okf:** full freshness audit of the .okf bundle ([2d16ceb](https://github.com/Landparty/jcl-parser/commit/2d16cebeaecc47458bcb6a4a088f322df4b6a197))
* **okf:** keep the audit-data field lists ruff-format clean ([6acbf51](https://github.com/Landparty/jcl-parser/commit/6acbf5172cc719afb01efbf9810e6c7a0e0db59f))
* **okf:** log the severity:medium issue fixes ([70aa532](https://github.com/Landparty/jcl-parser/commit/70aa532c7d23d3870e6e988065031f2b9b70755b))
* **okf:** refresh development pages (line counts, test/mypy counts, JES3 cards) ([d4834b3](https://github.com/Landparty/jcl-parser/commit/d4834b36c416f647e8290efe948a14f9f25e6477))
* point Documentation URL at .okf/, close AUDIT M7, merge duplicate log heading ([870dd29](https://github.com/Landparty/jcl-parser/commit/870dd29fb57a11289d812c678ecea0d79e08b86b))

## [2.0.3](https://github.com/Landparty/jcl-parser/compare/v2.0.2...v2.0.3) (2026-10-14)


### Bug Fixes

* **explosion:** a SET inside a PROC applies from where it is coded ([b64c0ab](https://github.com/Landparty/jcl-parser/commit/b64c0abebbe37185df55b6d64f5b69cf079db1e0))
* **explosion:** a SET inside a PROC applies from where it is coded ([086508d](https://github.com/Landparty/jcl-parser/commit/086508d7bd2eac8b1707dc9ee0b0fe0914f9f252))
* **explosion:** nested EXEC procname keeps && in symbolic values ([b1f16bd](https://github.com/Landparty/jcl-parser/commit/b1f16bdced312315726cda0b256e422404e63c59))
* **explosion:** nested EXEC procname keeps && in symbolic values ([61ea3c4](https://github.com/Landparty/jcl-parser/commit/61ea3c45e31ae131dc87f7477a20b6889daaf795))
* **sql:** only EXEC SQL utility statements are SQL in DSNUTILB input ([45bf2b2](https://github.com/Landparty/jcl-parser/commit/45bf2b2851b0980070007468e601f9c7b7d1487d))
* **sql:** only EXEC SQL utility statements are SQL in DSNUTILB input ([20c5623](https://github.com/Landparty/jcl-parser/commit/20c5623383695c23e9e54326ec3af5a7a09b9721))
* update author information in pyproject.toml ([35317e8](https://github.com/Landparty/jcl-parser/commit/35317e8e2738c3dfd1375a14ae2108dc486286e1))

## [2.0.2](https://github.com/Landparty/jcl-parser/compare/v2.0.1...v2.0.2) (2026-10-13)


### Bug Fixes

* cap chained symbol expansion at MAX_SYMBOL_VALUE_LENGTH ([921db7e](https://github.com/Landparty/jcl-parser/commit/921db7ef581af09b669bbce2dca4ee90e3baf6eb)), closes [#70](https://github.com/Landparty/jcl-parser/issues/70)
* cap chained symbol expansion; drop col-72 indicator on 72-char records ([#70](https://github.com/Landparty/jcl-parser/issues/70), [#80](https://github.com/Landparty/jcl-parser/issues/80)) ([b1c5a43](https://github.com/Landparty/jcl-parser/commit/b1c5a43d917fb5285d2ad7e593cd3290a65679ea))
* drop column-72 indicator on continued 72-character records ([ddd2b14](https://github.com/Landparty/jcl-parser/commit/ddd2b14d87a4f73fb738d3fbf1f6f826253d1e82)), closes [#80](https://github.com/Landparty/jcl-parser/issues/80)


### Documentation

* fold [#70](https://github.com/Landparty/jcl-parser/issues/70)/[#80](https://github.com/Landparty/jcl-parser/issues/80) log entries into the 2026-10-13 heading ([5d45af4](https://github.com/Landparty/jcl-parser/commit/5d45af40660163526f1dcc02612fad1ef22daedb))

## [2.0.1](https://github.com/Landparty/jcl-parser/compare/v2.0.0...v2.0.1) (2026-10-13)


### Bug Fixes

* a PROC step tested by an IF on an unexploded job may not have run ([85abe92](https://github.com/Landparty/jcl-parser/commit/85abe92e56d3d9370288c0fb2c9fa60696746a97))
* dataset checks read PROC-call DD overrides on an unexploded job ([a5f4dbd](https://github.com/Landparty/jcl-parser/commit/a5f4dbd7a84ed71c43fe1acc6bb81e08ff94686c))
* dataset checks read PROC-call DD overrides on an unexploded job ([db1e70e](https://github.com/Landparty/jcl-parser/commit/db1e70e8663cef25adee0bbd595d1083aab32f2d))
* keep a comment inside a continued parenthesised list out of the operands ([a780877](https://github.com/Landparty/jcl-parser/commit/a7808773016494b4028f0fd8248d433f91779df7))
* lifecycle forward-reference warning ignores the other branch of an IF ([685dacd](https://github.com/Landparty/jcl-parser/commit/685dacde883aa77eda4014e7595f3e558406c208))
* **profiles:** read IDCAMS commands after THEN/ELSE and `;` ([38dfa73](https://github.com/Landparty/jcl-parser/commit/38dfa73fb4e2edae26a9043f64bc9321d5dd9a9a))
* **profiles:** read IDCAMS commands after THEN/ELSE and `;` ([a30e409](https://github.com/Landparty/jcl-parser/commit/a30e4093b80682bb7173042bb543c6c84e439b08))
* **profiles:** read IKJEFT01 DSN/BIND notes from the commands, not comments ([b1e9c32](https://github.com/Landparty/jcl-parser/commit/b1e9c323193a75539699b67e3454a3fd3d19f848))
* **profiles:** read IKJEFT01 DSN/BIND notes from the commands, not comments ([8bfbfbb](https://github.com/Landparty/jcl-parser/commit/8bfbfbb87d9bea189d5add7ef3b0c4e6e440b815))

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
