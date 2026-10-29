# Changelog

## [0.25.2](https://github.com/gigaverse-app/pytest-obligation/compare/v0.25.1...v0.25.2) (2026-10-29)


### Performance

* **binding:** retain function identity during source inspection ([37aecd6](https://github.com/gigaverse-app/pytest-obligation/commit/37aecd670855c63acbc768a09f719cb7825b7d32))

## [0.25.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.25.0...v0.25.1) (2026-10-29)


### Bug fixes

* **django:** observe effective connection method overrides ([0cfa9bb](https://github.com/gigaverse-app/pytest-obligation/commit/0cfa9bbcf72c39509702e8e276036e9b77dd64a7))

## [0.25.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.24.0...v0.25.0) (2026-10-28)


### Features

* **contracts:** prove overlapping admissions and settlement interleavings ([#193](https://github.com/gigaverse-app/pytest-obligation/issues/193)) ([058358d](https://github.com/gigaverse-app/pytest-obligation/commit/058358d2ddf6c18821b1275c248aa4f69b864cf8))


### Bug fixes

* **reporting:** combine contract evidence from CI jobs ([#191](https://github.com/gigaverse-app/pytest-obligation/issues/191)) ([f5bf428](https://github.com/gigaverse-app/pytest-obligation/commit/f5bf4282638a0ad9ea2e153474ce787530e2f1fa))

## [0.24.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.23.0...v0.24.0) (2026-10-27)


### Features

* **contracts:** share regression, expiry and baseline controls ([87bc3a6](https://github.com/gigaverse-app/pytest-obligation/commit/87bc3a6ec006abf8cb80f01e8e49259d490676c0))

## [0.23.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.22.0...v0.23.0) (2026-10-27)


### Features

* **celery:** task_contract for an application's own task, recovery bound by the application ([#180](https://github.com/gigaverse-app/pytest-obligation/issues/180)) ([38b339c](https://github.com/gigaverse-app/pytest-obligation/commit/38b339c63cdeaf21891102d8e2c7650015fc41e5))
* **proofs:** verify provider waits preserve failure budgets ([18e554f](https://github.com/gigaverse-app/pytest-obligation/commit/18e554f954b9d231b44c1d30d5b237a6215a4940))
* **report:** an amber ? for counts a run did not record, and a title per lane ([#182](https://github.com/gigaverse-app/pytest-obligation/issues/182)) ([c7f1693](https://github.com/gigaverse-app/pytest-obligation/commit/c7f169300605b6d9e8b45573a55aacfd4e00c46e))


### Bug fixes

* **contracts:** validate regression sensitivity and separate declarations ([#186](https://github.com/gigaverse-app/pytest-obligation/issues/186)) ([08d68ee](https://github.com/gigaverse-app/pytest-obligation/commit/08d68eedabf0aea393ffd8917a7a872561f376ea))
* **plans:** recognize local equality in a nonleading index key ([494df85](https://github.com/gigaverse-app/pytest-obligation/commit/494df85ed875bb2559bdcb280e6e180aee7c90d2))
* **report:** one counting rule decides every number in the sticky ([#185](https://github.com/gigaverse-app/pytest-obligation/issues/185)) ([68378bb](https://github.com/gigaverse-app/pytest-obligation/commit/68378bbcaa3c2b2539277619df2df0a612fabf79))
* **report:** readable manifests across versions, one alert per status ([#184](https://github.com/gigaverse-app/pytest-obligation/issues/184)) ([5345ccd](https://github.com/gigaverse-app/pytest-obligation/commit/5345ccdb06019ca311df34a283b74bcba99c1dbd))

## [0.22.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.21.0...v0.22.0) (2026-10-25)


### Features

* **job-retry-limits:** prove provider waits across selection and stale delivery ([#178](https://github.com/gigaverse-app/pytest-obligation/issues/178)) ([92683e0](https://github.com/gigaverse-app/pytest-obligation/commit/92683e04fd7cdd2fd0e255425cc7ccf93bbf4df3))


### Bug fixes

* **celery:** observe each faulted run as its fault left it, so recovery inside the run counts ([#176](https://github.com/gigaverse-app/pytest-obligation/issues/176)) ([f270816](https://github.com/gigaverse-app/pytest-obligation/commit/f270816eda4d2feddfd82ab754d1bef2732f27a9))
* **profiles:** proof 2 refuses a history that discharged before the provider applied ([#175](https://github.com/gigaverse-app/pytest-obligation/issues/175)) ([7d99250](https://github.com/gigaverse-app/pytest-obligation/commit/7d99250b608021ea954317e884458e3f3b0c1f82))

## [0.21.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.20.0...v0.21.0) (2026-10-25)


### Features

* add faithful-fake building blocks and profile C acknowledged-effect proofs ([#164](https://github.com/gigaverse-app/pytest-obligation/issues/164)) ([471319e](https://github.com/gigaverse-app/pytest-obligation/commit/471319ef33fc5fba5c87871639a1b6fab40ecc32))
* **celery:** kill the pool child with SIGKILL and fill a real Redis broker (land [#165](https://github.com/gigaverse-app/pytest-obligation/issues/165) on main) ([#172](https://github.com/gigaverse-app/pytest-obligation/issues/172)) ([5b3abde](https://github.com/gigaverse-app/pytest-obligation/commit/5b3abdea509dacff05d8543ba1062e6f21f2909b))
* **preview:** show adoption reports without target repository setup ([#169](https://github.com/gigaverse-app/pytest-obligation/issues/169)) ([64cbf3d](https://github.com/gigaverse-app/pytest-obligation/commit/64cbf3d7ba97b7a25caa2812879cecaf8990c662))
* **report:** keep the report in a README block and write a shields.io badge ([#171](https://github.com/gigaverse-app/pytest-obligation/issues/171)) ([d2b281e](https://github.com/gigaverse-app/pytest-obligation/commit/d2b281e2138d5c80b9af867804d2c69cb81731b8))


### Bug fixes

* **report:** distinguish workflow failures from contract results ([#174](https://github.com/gigaverse-app/pytest-obligation/issues/174)) ([b7b1415](https://github.com/gigaverse-app/pytest-obligation/commit/b7b14155cac4d5d69b9d3caf11119dbf70adc79a))
* **reporting:** reject rooted cache inputs on Windows and pass the core suite there ([#170](https://github.com/gigaverse-app/pytest-obligation/issues/170)) ([4d657b8](https://github.com/gigaverse-app/pytest-obligation/commit/4d657b8809b7d9ee1d368f313d015c69928f8668))

## [0.20.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.19.2...v0.20.0) (2026-10-25)


### Features

* **celery:** bind worker histories with process_handoffs= and deprecate history= ([#161](https://github.com/gigaverse-app/pytest-obligation/issues/161)) ([d2b8ac2](https://github.com/gigaverse-app/pytest-obligation/commit/d2b8ac2dda5a1ebdd4805513606113b3db515ebb))
* **report:** publish fork PR evidence with an isolated renderer ([#162](https://github.com/gigaverse-app/pytest-obligation/issues/162)) ([6936ca6](https://github.com/gigaverse-app/pytest-obligation/commit/6936ca68ce5252e4387e8f14de8bdb076b6b4777))

## [0.19.2](https://github.com/gigaverse-app/pytest-obligation/compare/v0.19.1...v0.19.2) (2026-10-24)


### Bug fixes

* **report:** retain expected-failure diagnostics without inferring reproduction ([#158](https://github.com/gigaverse-app/pytest-obligation/issues/158)) ([2d9859e](https://github.com/gigaverse-app/pytest-obligation/commit/2d9859e561fc353db782ea1571b360ba11878c1e))

## [0.19.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.19.0...v0.19.1) (2026-10-24)


### Bug fixes

* **report:** expose known failures and reconcile suite identities ([#156](https://github.com/gigaverse-app/pytest-obligation/issues/156)) ([e12400b](https://github.com/gigaverse-app/pytest-obligation/commit/e12400bc5a01e395955831e9640053b75c79f12a))

## [0.19.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.18.0...v0.19.0) (2026-10-24)


### Features

* **mongodb:** observe complete production selections ([#150](https://github.com/gigaverse-app/pytest-obligation/issues/150)) ([31f4abf](https://github.com/gigaverse-app/pytest-obligation/commit/31f4abfa3a91c97547b16aa4d4643a06735dc195))
* **testing:** bind fact-derived fixed effects ([#154](https://github.com/gigaverse-app/pytest-obligation/issues/154)) ([1a502c0](https://github.com/gigaverse-app/pytest-obligation/commit/1a502c00028a9e88bb35866e4fdf42577ad3bf6a))


### Bug fixes

* **prefect:** preserve fault context and bind native cancellation ([#149](https://github.com/gigaverse-app/pytest-obligation/issues/149)) ([7c4405c](https://github.com/gigaverse-app/pytest-obligation/commit/7c4405c93d3f8c20e0fa3e6a430e9ac2abbdacd7))
* **testing:** exercise blocked gates through the actual sweep ([#151](https://github.com/gigaverse-app/pytest-obligation/issues/151)) ([dbab2be](https://github.com/gigaverse-app/pytest-obligation/commit/dbab2be0e5079955d2264b3844d3bda607b5fdda))
* **testing:** initialize fixtures for schedule evidence ([#153](https://github.com/gigaverse-app/pytest-obligation/issues/153)) ([34c1bfd](https://github.com/gigaverse-app/pytest-obligation/commit/34c1bfd6cbd8ce22da8aafe898af6efc86ea5f32))
* **testing:** observe retry waits in production runners ([#152](https://github.com/gigaverse-app/pytest-obligation/issues/152)) ([bc73dc5](https://github.com/gigaverse-app/pytest-obligation/commit/bc73dc51e1f894e2d12df340eabaf2fa6c01999f))

## [0.18.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.17.0...v0.18.0) (2026-10-24)


### Features

* **mongodb:** inspect production selection queries ([#147](https://github.com/gigaverse-app/pytest-obligation/issues/147)) ([6ee3f1b](https://github.com/gigaverse-app/pytest-obligation/commit/6ee3f1b7fa6a994e026236c9b3a2c28466d56d6e))


### Bug fixes

* **reporting:** include selection and exemption evidence ([#146](https://github.com/gigaverse-app/pytest-obligation/issues/146)) ([ec74566](https://github.com/gigaverse-app/pytest-obligation/commit/ec74566144a32b37638b1ce48989d9d84c17fbc0))
* **testing:** compare inline selections without inventing a page limit ([#148](https://github.com/gigaverse-app/pytest-obligation/issues/148)) ([123f229](https://github.com/gigaverse-app/pytest-obligation/commit/123f2294aa74464882f64deac8a59eb531d717a1))
* **testing:** distinguish gate identity from monotonic scheduling ([#145](https://github.com/gigaverse-app/pytest-obligation/issues/145)) ([e46a241](https://github.com/gigaverse-app/pytest-obligation/commit/e46a241eb6a8577a59e08f35f98241bf0173f384))
* **testing:** support independent evidence consumers and complete inventory ([#143](https://github.com/gigaverse-app/pytest-obligation/issues/143)) ([e230d38](https://github.com/gigaverse-app/pytest-obligation/commit/e230d380c7817d9ddce773aa95a3ac36231b142e))

## [0.17.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.16.1...v0.17.0) (2026-10-24)


### Features

* **interleavings:** generate recreation and rejected-command histories ([#141](https://github.com/gigaverse-app/pytest-obligation/issues/141)) ([3323c29](https://github.com/gigaverse-app/pytest-obligation/commit/3323c2986ec72c3cc90ff64a7be17e66c015def3))

## [0.16.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.16.0...v0.16.1) (2026-10-24)

### Performance

* **report:** reuse content-keyed application inventories and avoid repeated virtual-environment scans ([71e2293](https://github.com/gigaverse-app/pytest-obligation/commit/71e22939ab999bd7d62397c2df85c14080825c89)).


### Bug fixes

* **release:** keep stable v1 actions current ([c866b13](https://github.com/gigaverse-app/pytest-obligation/commit/c866b138d61aff31b80f4f121459000e700ba7a7))

## [0.16.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.15.0...v0.16.0) (2026-10-24)


### Features

* **report:** separate defects, unassessed coverage and exclusions ([f759e9d](https://github.com/gigaverse-app/pytest-obligation/commit/f759e9d54cdb4f2abfd2a651400a480568001402))


### Bug fixes

* **report:** preserve visual hierarchy in large sticky reports ([3d137a5](https://github.com/gigaverse-app/pytest-obligation/commit/3d137a57a340e677e3d33235921afae1183dd3ca))

## [0.15.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.14.2...v0.15.0) (2026-10-23)


### Features

* report contract completeness and recovery diagnostics ([#119](https://github.com/gigaverse-app/pytest-obligation/issues/119)) ([70c5163](https://github.com/gigaverse-app/pytest-obligation/commit/70c5163ecb4ad220f4cb9074e6ad65a494dc35e8))
* **reporting:** explain contract evidence in a PR sticky action ([#122](https://github.com/gigaverse-app/pytest-obligation/issues/122)) ([4a59760](https://github.com/gigaverse-app/pytest-obligation/commit/4a5976098597b3028f529ce3b1360f06ba44d28d))
* **shopify:** add a Shopify billing simulator with independent provider evidence ([8b6b5fb](https://github.com/gigaverse-app/pytest-obligation/commit/8b6b5fb03a0a4002c8070ab67a92ce56fcabe509))


### Bug fixes

* **ci:** select all runtime tests by declared dependencies ([a52a9ec](https://github.com/gigaverse-app/pytest-obligation/commit/a52a9ec3a66f8391d72c0f3db3385064bca38d22))

## [0.14.2](https://github.com/gigaverse-app/pytest-obligation/compare/v0.14.1...v0.14.2) (2026-10-23)


### Bug fixes

* Support PyMongo 4.18 bulk-write and read-checkout boundaries while preserving 4.9 through 4.17 compatibility ([#109](https://github.com/gigaverse-app/pytest-obligation/pull/109)).
* Adopt compatible CI-esta and pytest-selective releases, including the matching PostgreSQL client repair.

### Performance

* **ci:** repair snapshots and reduce Saleor recovery overhead ([#108](https://github.com/gigaverse-app/pytest-obligation/issues/108)) ([ad67e0f](https://github.com/gigaverse-app/pytest-obligation/commit/ad67e0fe3911091ece8537b8b61a4436ef50b323))
* parallelize Wagtail and Due conformance with isolated databases ([#105](https://github.com/gigaverse-app/pytest-obligation/issues/105)) ([533bf3c](https://github.com/gigaverse-app/pytest-obligation/commit/533bf3c23bf92d6dbf215d7e1a9104a71277d049))


### Documentation

* replace sister-project sections with footer badges ([#99](https://github.com/gigaverse-app/pytest-obligation/issues/99)) ([8c325d6](https://github.com/gigaverse-app/pytest-obligation/commit/8c325d67a572987e8a0cd2bb9d0ef3dfeec20ba2))
* show the CI-esta logo on the CI-esta badge ([#102](https://github.com/gigaverse-app/pytest-obligation/issues/102)) ([ecd9305](https://github.com/gigaverse-app/pytest-obligation/commit/ecd9305a4fa35398d8dddbbad987a109aeff75bc))

## [0.14.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.14.0...v0.14.1) (2026-10-22)


### Documentation

* connect CI-esta observability and evidence reuse ([#90](https://github.com/gigaverse-app/pytest-obligation/issues/90)) ([920f138](https://github.com/gigaverse-app/pytest-obligation/commit/920f1380d20a18ad9d026d1a84c9d931c3138785))

## [0.14.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.13.1...v0.14.0) (2026-10-21)


### Features

* enforce recovery proof coverage and share failing-page histories ([#85](https://github.com/gigaverse-app/pytest-obligation/issues/85)) ([2f9009a](https://github.com/gigaverse-app/pytest-obligation/commit/2f9009a46952b582b3a8e6a65bb6be381341ceec))

## [0.13.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.13.0...v0.13.1) (2026-10-13)


### Bug fixes

* reject a negative provider request lifetime or elapsed time ([#82](https://github.com/gigaverse-app/pytest-obligation/issues/82)) ([bbe0a10](https://github.com/gigaverse-app/pytest-obligation/commit/bbe0a1028d6d4035982abd52ff4760ee8cf73415))

## [0.13.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.12.1...v0.13.0) (2026-10-13)


### Features

* interleavings model provider request lifetimes and declared repair windows ([#80](https://github.com/gigaverse-app/pytest-obligation/issues/80)) ([25bdbf0](https://github.com/gigaverse-app/pytest-obligation/commit/25bdbf047f0cbd0736cb54b32ab3e2a5ccecc1f4))

## [0.12.1](https://github.com/gigaverse-app/pytest-obligation/compare/v0.12.0...v0.12.1) (2026-10-12)


### Bug fixes

* an identity probe through a unique key passes the index-served verdict ([#78](https://github.com/gigaverse-app/pytest-obligation/issues/78)) ([12a917b](https://github.com/gigaverse-app/pytest-obligation/commit/12a917b291cd6abe0adf6da4cccd8bcb27b04744))

## [0.12.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.11.0...v0.12.0) (2026-10-12)


### ⚠ BREAKING CHANGES

* the index-served verdict requires the selection's own narrowing ([#74](https://github.com/gigaverse-app/pytest-obligation/issues/74))

### Features

* owed-row loops bind external-resource identities through a listing seam ([#76](https://github.com/gigaverse-app/pytest-obligation/issues/76)) ([ccf6b67](https://github.com/gigaverse-app/pytest-obligation/commit/ccf6b674d5bdc7d28e8a75c691b2eba5c74c2c81))
* polling selections prove isolation and per-tick service through generated owed-row cases ([#73](https://github.com/gigaverse-app/pytest-obligation/issues/73)) ([5bc5557](https://github.com/gigaverse-app/pytest-obligation/commit/5bc555741ca4a41154d91421da2b43b5c2e3789e))
* prove bounded terminal completion and duplicate delivery separately ([#77](https://github.com/gigaverse-app/pytest-obligation/issues/77)) ([f2ae3c6](https://github.com/gigaverse-app/pytest-obligation/commit/f2ae3c6d0fde9b52796dade2dd05e8567b9513de))
* the index-served verdict requires the selection's own narrowing ([#74](https://github.com/gigaverse-app/pytest-obligation/issues/74)) ([78ba059](https://github.com/gigaverse-app/pytest-obligation/commit/78ba0599b0fc7e5b2cc8727f50ea80633fd00e53))


### Bug fixes

* carry canonical Ruff rules with the editable package ([#70](https://github.com/gigaverse-app/pytest-obligation/issues/70)) ([67d0ed2](https://github.com/gigaverse-app/pytest-obligation/commit/67d0ed2461d331ced149c95c8943260be87463db))

## [0.11.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.10.0...v0.11.0) (2026-10-12)


### Features

* deliver scheduled selection extras on main ([#65](https://github.com/gigaverse-app/pytest-obligation/issues/65)) ([82a3310](https://github.com/gigaverse-app/pytest-obligation/commit/82a33107ab9552519c320a202fc32f10159991b7))
* profile J proves each named provider outcome gets its declared classification ([#63](https://github.com/gigaverse-app/pytest-obligation/issues/63)) ([6f89fb8](https://github.com/gigaverse-app/pytest-obligation/commit/6f89fb8ecc9f75e680f66e886af6df0d5574ab91))
* profile J proves unbounded retry keeps the obligation owed ([#61](https://github.com/gigaverse-app/pytest-obligation/issues/61)) ([4638b3a](https://github.com/gigaverse-app/pytest-obligation/commit/4638b3a11d7c81dfef030a2148bd78d366c93a21))
* require outcomes in generated replay contracts ([#59](https://github.com/gigaverse-app/pytest-obligation/issues/59)) ([5d9de46](https://github.com/gigaverse-app/pytest-obligation/commit/5d9de46494e4101687bade37cfee17c3f50355c8))


### Bug fixes

* authenticate release PRs from a main-only environment ([#66](https://github.com/gigaverse-app/pytest-obligation/issues/66)) ([696719d](https://github.com/gigaverse-app/pytest-obligation/commit/696719d840589fb11f94e8a38cc69ce502f595ef))
* wait for normal CI before publishing manual releases ([#62](https://github.com/gigaverse-app/pytest-obligation/issues/62)) ([0bd60e5](https://github.com/gigaverse-app/pytest-obligation/commit/0bd60e537b2d6ba69f794883a356969947bc8b98))

## [0.10.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.9.0...v0.10.0) (2026-10-12)


### Features

* complete backend harness port and migration parity checks ([#50](https://github.com/gigaverse-app/pytest-obligation/issues/50)) ([fbe0b5a](https://github.com/gigaverse-app/pytest-obligation/commit/fbe0b5ad528bbd662a8db5a8e4876309b96a91f6))
* enforce application outcomes through reusable contract bindings ([#56](https://github.com/gigaverse-app/pytest-obligation/issues/56)) ([5d6e01c](https://github.com/gigaverse-app/pytest-obligation/commit/5d6e01cd6965e80d8883a9580fe7085ae5fdd84b))
* preserve current BE harness guarantees and debt controls ([#53](https://github.com/gigaverse-app/pytest-obligation/issues/53)) ([53a1222](https://github.com/gigaverse-app/pytest-obligation/commit/53a1222a6eecad0219e320f363d05b94727aaf30))
* preserve scoped hosts and shared delivery proofs ([#55](https://github.com/gigaverse-app/pytest-obligation/issues/55)) ([8825ab8](https://github.com/gigaverse-app/pytest-obligation/commit/8825ab8e649c93c58ec6ad5f1a484b2ff7df344f))
* prove recovery selection completeness ([#54](https://github.com/gigaverse-app/pytest-obligation/issues/54)) ([7d8be37](https://github.com/gigaverse-app/pytest-obligation/commit/7d8be37b083983691f7e7bbc4793cc9e4b772865))


### Bug fixes

* preserve proof failures and complete shared harness contracts ([#57](https://github.com/gigaverse-app/pytest-obligation/issues/57)) ([ba59710](https://github.com/gigaverse-app/pytest-obligation/commit/ba59710b5248ca8d68aed14599d417b0467289b8))

## [0.9.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.8.0...v0.9.0) (2026-10-11)


### ⚠ BREAKING CHANGES

* port recovery isolation and owed-row conformance checks ([#46](https://github.com/gigaverse-app/pytest-obligation/issues/46))

### Features

* inject and detect acknowledgement without application on opted-in seams ([#40](https://github.com/gigaverse-app/pytest-obligation/issues/40)) ([e7f5d46](https://github.com/gigaverse-app/pytest-obligation/commit/e7f5d46df31e131b14489f2f11a599a1f6fa6709))
* port recovery isolation and owed-row conformance checks ([#46](https://github.com/gigaverse-app/pytest-obligation/issues/46)) ([8c60ebb](https://github.com/gigaverse-app/pytest-obligation/commit/8c60ebb4279f0825e13f33e0bc992fb09198f70a))
* support scoped handoff arrangements ([#49](https://github.com/gigaverse-app/pytest-obligation/issues/49)) ([fae502e](https://github.com/gigaverse-app/pytest-obligation/commit/fae502e90cc4a957e1bb4da7021a4a2d55f86ede))

## [0.8.0](https://github.com/gigaverse-app/pytest-obligation/compare/v0.7.0...v0.8.0) (2026-10-01)


### ⚠ BREAKING CHANGES

* rename project to pytest-obligation ([#42](https://github.com/gigaverse-app/pytest-obligation/issues/42))
* port backend interleavings and unified A–J profiles ([#34](https://github.com/gigaverse-app/pytest-obligation/issues/34))

### Features

* add Due Work Harness plugin for Codex and Claude ([#39](https://github.com/gigaverse-app/pytest-obligation/issues/39)) ([5091717](https://github.com/gigaverse-app/pytest-obligation/commit/50917176363768ca2ccff86ad5f6f4addaa01b42))
* exercise generated guarantees across shipped adopters ([#36](https://github.com/gigaverse-app/pytest-obligation/issues/36)) ([f4de472](https://github.com/gigaverse-app/pytest-obligation/commit/f4de47278c3f068c80eb3b5b8713b0d055fc1698))
* introduce ObligationContract with isolated legacy shims ([#44](https://github.com/gigaverse-app/pytest-obligation/issues/44)) ([d3c2df6](https://github.com/gigaverse-app/pytest-obligation/commit/d3c2df6b3b35550641a162152171773354687d84))
* port backend interleavings and unified A–J profiles ([#34](https://github.com/gigaverse-app/pytest-obligation/issues/34)) ([599b183](https://github.com/gigaverse-app/pytest-obligation/commit/599b1839fb2b6dfce12152673dbf1f707c156525))
* rename project to pytest-obligation ([#42](https://github.com/gigaverse-app/pytest-obligation/issues/42)) ([73ab229](https://github.com/gigaverse-app/pytest-obligation/commit/73ab2292771c4a1a8f477c2723e9ccb8b6509d78))


### Documentation

* promote pytest plugin adoption and discovery ([#41](https://github.com/gigaverse-app/pytest-obligation/issues/41)) ([6258939](https://github.com/gigaverse-app/pytest-obligation/commit/6258939c58f1acf8bd065e163aa6a45b3de64efe))

## [0.7.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.6.0...v0.7.0) (2026-09-30)


### ⚠ BREAKING CHANGES

* four ways a suite that passed can now fail: a test-written probe that swallows an assertion through a broad handler or an alias fails contract validation; a declared handoff gap that xfailed for a reason other than the divergence fails as that reason; a history, in-process or process, whose observation differs between two clean runs is refused; and after an injected failure, an error raised in its handler without `from` fails the history. `assert_histories_converge` no longer accepts `divergence=`.

### Features

* add aiokafka offset faults and shared worker death fencing ([#33](https://github.com/gigaverse-app/due-work-harness/issues/33)) ([0753c30](https://github.com/gigaverse-app/due-work-harness/commit/0753c302ce170aa68e91851133b47b2a58f8ff92))
* add Prefect flow-body and recurrence bindings ([#32](https://github.com/gigaverse-app/due-work-harness/issues/32)) ([00c0c68](https://github.com/gigaverse-app/due-work-harness/commit/00c0c687768eda5f571edc2b444df1d7a7af3508))
* backend round fixes: inversion tripwire, handoff gaps, repeated normal operation, one absorption rule, tiny-table plans ([#29](https://github.com/gigaverse-app/due-work-harness/issues/29)) ([4be0656](https://github.com/gigaverse-app/due-work-harness/commit/4be0656ad4b46b28f2bbb719b707d66e56b42d26))
* interrupt MongoDB writes in async application histories ([#31](https://github.com/gigaverse-app/due-work-harness/issues/31)) ([06c982e](https://github.com/gigaverse-app/due-work-harness/commit/06c982e994b1c022a51dd60458cd809923283ded))
* support Python 3.11 for core conformance proofs ([#35](https://github.com/gigaverse-app/due-work-harness/issues/35)) ([a212ec0](https://github.com/gigaverse-app/due-work-harness/commit/a212ec0f895897930fdc2b7833262e97471b8d85))

## [0.6.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.5.2...v0.6.0) (2026-09-29)


### ⚠ BREAKING CHANGES

* `ExternalCall` seams now accept only plain results and coroutines. A seam whose call returns an async generator, a generator, an asyncio Task or Future, a `concurrent.futures.Future` or another non-coroutine awaitable raises `DueWorkContractDesignError` naming the seam; declare the coroutine method that performs the effect instead. `main` passed such a result through and counted the call when it returned. One function declared through overlapping owners is refused too. The Django commit observer now counts a `DO` block, and a zero-row `INSERT`/`UPDATE`/`DELETE`/`MERGE` whose trigger or predicate function writes, as commits: histories that pin `Findings` by commit number (`worker died after commit N`) may need re-recording.

### Features

* **coverage:** in-transaction lists handoffs made inside transaction.atomic() ([#26](https://github.com/gigaverse-app/due-work-harness/issues/26)) ([db152dc](https://github.com/gigaverse-app/due-work-harness/commit/db152dc54aec2e568d5b267fdfaab4a110095dce))
* execution-eligibility profile and the backend's hardened write, seam and race proofs ([#28](https://github.com/gigaverse-app/due-work-harness/issues/28)) ([9c871c1](https://github.com/gigaverse-app/due-work-harness/commit/9c871c18eea897f308d3ccd3cbcb917541e1a217))
* record findings, management_command recovery, clear PostgreSQL-only error ([#25](https://github.com/gigaverse-app/due-work-harness/issues/25)) ([9ccf4f4](https://github.com/gigaverse-app/due-work-harness/commit/9ccf4f43782abff5f29da82e812f64d3dec88061))

## [0.5.2](https://github.com/gigaverse-app/due-work-harness/compare/v0.5.1...v0.5.2) (2026-09-29)


### Documentation

* the upstream playbook and a skill, for repeating the find-and-disclose cycle ([#21](https://github.com/gigaverse-app/due-work-harness/issues/21)) ([9cc0639](https://github.com/gigaverse-app/due-work-harness/commit/9cc06397d36ca53c15bfb06a11cb6e12f3b5f7cb))

## [0.5.1](https://github.com/gigaverse-app/due-work-harness/compare/v0.5.0...v0.5.1) (2026-09-29)


### Bug fixes

* **django:** run the autocommit-write probe through a DB-API cursor, so psycopg2 works ([#22](https://github.com/gigaverse-app/due-work-harness/issues/22)) ([d383885](https://github.com/gigaverse-app/due-work-harness/commit/d383885e2e367c42a53eb227be945aaca98df13f))

## [0.5.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.4.0...v0.5.0) (2026-09-28)


### Features

* **contract:** histories declare their findings, one run per history set ([#19](https://github.com/gigaverse-app/due-work-harness/issues/19)) ([301ada7](https://github.com/gigaverse-app/due-work-harness/commit/301ada78f358bfc0f36c320bbf95cf2d06b26348))

## [0.4.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.3.0...v0.4.0) (2026-09-28)


### Features

* **process-histories:** one child fault protocol for every process history ([5835ac1](https://github.com/gigaverse-app/due-work-harness/commit/5835ac13ded76360f8a7ba4dc24f81f72a5d2653))
* **pytest:** --due-work-summary lists what each generated suite produced ([5835ac1](https://github.com/gigaverse-app/due-work-harness/commit/5835ac13ded76360f8a7ba4dc24f81f72a5d2653))

## [0.3.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.2.0...v0.3.0) (2026-09-28)


### Features

* **integrations:** Redis, RQ and Celery's real worker, with lost-reply and survivable-failure histories ([#15](https://github.com/gigaverse-app/due-work-harness/issues/15)) ([93ba16d](https://github.com/gigaverse-app/due-work-harness/commit/93ba16dd697f8202af32b987b06b2dc7623b3f18))


### Bug fixes

* **demos:** the Saleor run's version fallback actually applies ([6e1cf41](https://github.com/gigaverse-app/due-work-harness/commit/6e1cf4189c6c0f241648eb1e386cb37f9eb3b8b5))

## [0.2.0](https://github.com/gigaverse-app/due-work-harness/compare/v0.1.1...v0.2.0) (2026-09-28)


### Features

* assert_pinned_outcomes for findings tables, and due_work_database for hand-written tests ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))
* **crash-histories:** fail each signal receiver in turn ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))
* **demos:** Wagtail 8.0 on django-tasks-db, unmodified from PyPI ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))
* **django-tasks:** django-tasks-db integration, its worker as recovery and its own worker contract ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))
* **django:** serialized_rollback for projects whose migrations seed rows ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))


### Bug fixes

* **celery:** count a non-eager publication once ([c18e37b](https://github.com/gigaverse-app/due-work-harness/commit/c18e37bc4bc15be26c41272c02dd173a4997b30b))


### Documentation

* embed the explainer and findings videos in the README ([#11](https://github.com/gigaverse-app/due-work-harness/issues/11)) ([f320002](https://github.com/gigaverse-app/due-work-harness/commit/f320002c7b26471c6e23b3e0f564dc9ab975f101))

## [0.1.1](https://github.com/gigaverse-app/due-work-harness/compare/v0.1.0...v0.1.1) (2026-09-28)


### Bug fixes

* **verify:** only the xdist controller verifies declared suites ([c628f16](https://github.com/gigaverse-app/due-work-harness/commit/c628f16492251733bf9f2bd75f1cf1fb4b983b20))


### Documentation

* a recorded demo GIF of the harness finding real bugs, and a README rewrite ([#8](https://github.com/gigaverse-app/due-work-harness/issues/8)) ([3e2f6a0](https://github.com/gigaverse-app/due-work-harness/commit/3e2f6a0a285143a87c1859865d0c4f9a83a58851))

## 0.1.0 (2026-09-28)


### Features

* **coverage:** find Dramatiq, RQ and Django task handoffs, and Celery's on-commit sends ([f03622f](https://github.com/gigaverse-app/due-work-harness/commit/f03622fd93d1af71b78a541d47e1a18b7cd18123))
* **coverage:** scan source roots outside the project's directory ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **crash-histories:** fail each after-commit callback in turn ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **crash-histories:** the broker refuses each publication in turn ([df8b17f](https://github.com/gigaverse-app/due-work-harness/commit/df8b17f62f44ed0db1abd2ffd862efbb19392d96))
* **demos:** DBOS and Saleor claim what their frameworks provide ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **demos:** every demo adopts the harness through contracts ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **demos:** Saleor claims recovery, its selection observed from the tick it runs ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **demos:** Saleor's checkout, unmodified, loses charges and confirmations ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **ownership:** prove every owner write is fenced, not only the settlement ([df8b17f](https://github.com/gigaverse-app/due-work-harness/commit/df8b17f62f44ed0db1abd2ffd862efbb19392d96))
* **procrastinate:** claim ownership, retention, replay and retry against procrastinate itself ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* publish to PyPI with SemVer releases cut from Conventional Commits ([#2](https://github.com/gigaverse-app/due-work-harness/issues/2)) ([8156135](https://github.com/gigaverse-app/due-work-harness/commit/8156135a433683d34848afbca89dfcee82b4af75))


### Bug fixes

* **check-action:** keep the check's Python out of the caller's job ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **contract:** probes run with the contract's database; rewritten asserts are not inversions ([1c8492d](https://github.com/gigaverse-app/due-work-harness/commit/1c8492df3f8e45c7e34ca201f0a9169fe7ec1e55))
* **procrastinate:** poll for a reclaimed job while it is due within the skew ([df8b17f](https://github.com/gigaverse-app/due-work-harness/commit/df8b17f62f44ed0db1abd2ffd862efbb19392d96))
