# 第三方数据、字体和库

小梦的词书的程序代码以 MIT 许可证发布（见 `LICENSE`）。仓库里附带的词典数据和字体来自下面这些项目，
它们各自的许可证继续适用。再分发本项目（包括打包成 exe）时，请保留这份文件。

## 内置数据

| 文件 | 内容 | 来源 | 许可证 |
|---|---|---|---|
| `shici/data/dict_en.db`（entries、forms、books 表） | 英语释义、音标、词频、考试标签 | [ECDICT](https://github.com/skywind3000/ECDICT)，Copyright (c) Linwei | MIT |
| `shici/data/dict_en.db`（sentences、examples 表） | 英汉例句，保留了 Tatoeba 句子编号 | [Tatoeba](https://tatoeba.org) | CC BY 2.0 FR |
| `shici/data/dict_en.db`（sid 为负数的 sentences） | 生僻词的用法示例 | [WordNet 3.0](https://wordnet.princeton.edu/)，Copyright 2006 Princeton University | WordNet License（见下） |
| `shici/data/dict_en.db`（sid 为负数且带中文译文的 sentences）、`tools/extra_examples_en.tsv` | 约 800 个生僻词的例句和译文 | 本项目自己编写 | 与程序代码相同（MIT） |
| `shici/data/dict_ja.db`（sentences、examples 表） | 日语例句及中文 / 英文译文 | [Tatoeba](https://tatoeba.org) | CC BY 2.0 FR |
| `shici/data/audio_en.db` | 英语单词发音（合成语音） | 用 [Piper](https://github.com/rhasspy/piper)（MIT）和语音模型 `en_US-ljspeech-medium` 生成；模型训练自 [LJ Speech](https://keithito.com/LJ-Speech-Dataset/) 数据集 | 数据集为公有领域 |
| `shici/data/audio_ja.db` | 日语单词发音（合成语音） | 用 [Open JTalk](https://open-jtalk.sp.nitech.ac.jp/)（Modified BSD）和 HTS voice “Mei”（MMDAgent 项目，名古屋工业大学）生成 | 语音模型 CC BY 3.0 |
| `shici/data/dict_ja.db`（词表） | JLPT N5–N1 词表 | Jonathan Waller, [tanos.co.uk/jlpt](https://www.tanos.co.uk/jlpt/)，经 [Bluskyo/JLPT_Vocabulary](https://github.com/Bluskyo/JLPT_Vocabulary) 整理 | CC BY |
| `shici/data/dict_ja.db`（释义） | 日语词的英文释义 | [JMdict](https://www.edrdg.org/wiki/index.php/JMdict-EDICT_Dictionary_Project)，Electronic Dictionary Research and Development Group | CC BY-SA 4.0 |
| `shici/data/dict_ja.db`（`translation_zh`，`zh_src` 为 wikt / pivot） | 日语词的中文释义 | [维基词典](https://zh.wiktionary.org/)（中文版日语词条；英文版翻译表），经 [kaikki.org](https://kaikki.org/) / wiktextract 提取 | CC BY-SA 4.0 |
| `shici/data/dict_ja.db`（`translation_zh`，`zh_src` 为 ecdict） | 程序根据英文释义自动匹配的中文 | 由 JMdict 英文释义对照 ECDICT 生成 | 同上两者 |
| `shici/data/dict_en.db`（`entries.translation_ja`） | 英语词的日语释义 | [EJDict-hand](https://github.com/kujirahand/EJDict) | 公有领域（Public Domain） |
| `shici/data/dict_en.db`（`sentences.ja`） | 英语例句的日语译文 | [Tatoeba](https://tatoeba.org) | CC BY 2.0 FR |
| 两个词典里 `mt = 1` 的例句译文 | 机器翻译的中文译文 | 用 [opus-mt-en-zh](https://huggingface.co/Helsinki-NLP/opus-mt-en-zh)（Helsinki-NLP，CC BY 4.0）翻译 Tatoeba / WordNet 的英文句子 | 跟随原句许可证 |

说明：

- 例句经过筛选（长度、是否有译文），繁体译文用 OpenCC 转成了简体。每条 Tatoeba 例句的原始页面是
  `https://tatoeba.org/sentences/show/<sid>`，`sid` 存在 `sentences` 表里（英语库里 `sid` 为负数的不是 Tatoeba 的句子：没有译文的是 WordNet 的用法示例，带中文译文的是本项目自己编写的例句）。
- 语音包是用上面两套开源语音合成工具提前生成的音频，不包含合成引擎和模型本身。怎么生成的见 `tools/build_audio.py`。
- JLPT 没有官方词表，这里用的是社区整理的版本，和实际考试范围不保证一致。
- `dict_ja.db` 含 CC BY-SA 4.0 数据：如果你修改并再分发这个数据库，需要以相同许可证发布修改后的数据库。
  这不影响程序代码的 MIT 许可证。
- 数据怎么生成的见 `tools/build_dict.py`；中文 / 日语释义和机翻译文见 `tools/build_bilingual.py`、`tools/wikt_ja_zh.py`、`tools/enwikt_pivot.py`、`tools/mt_sentences.py`。

### WordNet License

WordNet Release 3.0. This software and database is being provided to you, the LICENSEE, by Princeton University under the
following license. By obtaining, using and/or copying this software and database, you agree that you have read, understood,
and will comply with these terms and conditions.:

Permission to use, copy, modify and distribute this software and database and its documentation for any purpose and without
fee or royalty is hereby granted, provided that you agree to comply with the following copyright notice and statements,
including the disclaimer, and that the same appear on ALL copies of the software, database and documentation, including
modifications that you make for internal use or for distribution.

WordNet 3.0 Copyright 2006 by Princeton University. All rights reserved.

THIS SOFTWARE AND DATABASE IS PROVIDED "AS IS" AND PRINCETON UNIVERSITY MAKES NO REPRESENTATIONS OR WARRANTIES, EXPRESS OR
IMPLIED. BY WAY OF EXAMPLE, BUT NOT LIMITATION, PRINCETON UNIVERSITY MAKES NO REPRESENTATIONS OR WARRANTIES OF MERCHANT-
ABILITY OR FITNESS FOR ANY PARTICULAR PURPOSE OR THAT THE USE OF THE LICENSED SOFTWARE, DATABASE OR DOCUMENTATION WILL NOT
INFRINGE ANY THIRD PARTY PATENTS, COPYRIGHTS, TRADEMARKS OR OTHER RIGHTS.

The name of Princeton University or Princeton may not be used in advertising or publicity pertaining to distribution of the
software and/or database. Title to copyright in this software, database and any associated documentation shall at all times
remain with Princeton University and LICENSEE agrees to preserve same.

## 字体（`shici/web/fonts/`）

均为 SIL Open Font License 1.1，许可证全文在同目录的 `OFL-*.txt`。字体做过裁剪（只保留界面用到的字符）。

| 文件 | 原字体 |
|---|---|
| `serif.woff2` | Noto Serif SC |
| `serif-jp.woff2` | Noto Serif JP |
| `sans.woff2` | Inter |
| `mono.woff2` | JetBrains Mono |

## 运行时依赖（通过 pip 安装，不在仓库里）

| 库 | 用途 | 许可证 |
|---|---|---|
| [py-fsrs](https://github.com/open-spaced-repetition/py-fsrs) | FSRS 记忆调度算法 | MIT |
| [PySide6](https://doc.qt.io/qtforpython-6/) | 桌面窗口、Qt WebEngine、系统语音 | LGPL-3.0 |
| [openpyxl](https://openpyxl.readthedocs.io/) | 读取 .xlsx 词表 | MIT |

## 在线发音

两种情况下程序会向有道词典的公开发音地址（`dict.youdao.com/dictvoice`）请求音频，并缓存在本机：
发音来源选了“在线真人”；或者要读的词不在内置语音包里，而且“联网补充”开着（默认开）。
这不是官方开放接口，随时可能失效；失效或断网时程序会改用内置语音或系统语音。

## 标志

`shici/web/img/` 里的 L.Dream 标志是作者的个人标志，不在 MIT 许可范围内；基于本项目再发布时请换成自己的图标。
