"""词根、前缀、后缀表（本项目自己整理，随项目以 MIT 许可证发布）。

每行：拼写形式 | 中文意思 | 来源 | 词源里要出现的拉丁语 / 希腊语词干
最后一栏用来核对：只有维基词典的词源里确实出现了这些词干之一，才认为某个单词含有这个词根，
避免「cap 在 capacity 里是不是“抓”」这类只看拼写的误判。希腊语按拉丁转写写（kh / ch、k / c、y / u 都列上）。
"""

ROOTS = """
act, ag | 做、驱动 | 拉丁语 agere | agere, agens, agent, actus, actio, actum, activ, agit
aer | 空气 | 希腊语 aer | aer
agr | 田地 | 拉丁语 ager | agri, ager
alter, altern | 其他、交替 | 拉丁语 alter | alter
alt | 高 | 拉丁语 altus | altus, altit, altare
ambul | 行走 | 拉丁语 ambulare | ambul
am, amor, amat | 爱 | 拉丁语 amare | amare, amor, amat, amic, amabil
anim | 生命、心神 | 拉丁语 anima | anim
ann, enn | 年 | 拉丁语 annus | annus, annu, ennis, ennium, annal
anthrop | 人 | 希腊语 anthropos | anthrop
apt | 适合 | 拉丁语 aptus | aptus, aptare, aptit
aqu | 水 | 拉丁语 aqua | aqu
arch | 统治、首要 | 希腊语 arkhein | arkh, arch
arm | 武器 | 拉丁语 arma | arma, armat
art | 技艺 | 拉丁语 ars | artis, artem, ars, artif
astr, aster | 星 | 希腊语 astron | astr, aster
aud, audit | 听 | 拉丁语 audire | aud
bat | 打 | 拉丁语 battuere | batt
bell | 战争 | 拉丁语 bellum | bellum, belli, bellat, bellare, rebell
bibl | 书 | 希腊语 biblion | bibl
bio | 生命 | 希腊语 bios | bio
brev | 短 | 拉丁语 brevis | brev
cad, cas, cid | 落下、发生 | 拉丁语 cadere | cadere, cado, cadens, casus, cadent
cand | 发白、发光 | 拉丁语 candere | candere, candid, candor, candel, candidat
cant, chant | 唱 | 拉丁语 cantare | cantare, canto, cantat, cantic, cantor, chanter, chant
capit | 头 | 拉丁语 caput | capit, caput
cap, capt, cept, ceiv, cip | 拿、抓 | 拉丁语 capere | capere, capio, capt, cept, cipere, cipio, capac, capax, cipi
carn | 肉 | 拉丁语 caro | carn
caus, cus | 原因 | 拉丁语 causa | caus
cav | 洞、空 | 拉丁语 cavus | cav
ced, ceed, cess | 走、让步 | 拉丁语 cedere | cedere, cedo, cess
celer | 快 | 拉丁语 celer | celer, celerit, celerare, celerat
centr | 中心 | 拉丁语 centrum | centr, kentr
cent | 百 | 拉丁语 centum | centum, centen, centes, centi
cern | 分辨 | 拉丁语 cernere | cern
cert | 确定 | 拉丁语 certus | cert
chrom | 颜色 | 希腊语 khroma | khrom, chrom
chron | 时间 | 希腊语 khronos | khron, chron
cid, cis | 切、杀 | 拉丁语 caedere | caed, cisus, cisio, cida, cidium
circ | 环、圆 | 拉丁语 circus | circ
cit | 唤起、引用 | 拉丁语 citare | citare, citat, cito
civ | 公民 | 拉丁语 civis | civ
claim, clam | 喊叫 | 拉丁语 clamare | clam
clar | 清楚、明亮 | 拉丁语 clarus | clar
clin | 倾斜 | 拉丁语 clinare | clin, klin
clud, clus, clos | 关闭 | 拉丁语 claudere | claud, clud, claus, clus
cogn | 知道 | 拉丁语 cognoscere | cogn
cord | 心 | 拉丁语 cor | cord
corpor, corp | 身体 | 拉丁语 corpus | corp
cosm | 宇宙、秩序 | 希腊语 kosmos | kosm, cosm
crat, crac | 统治 | 希腊语 kratos | krat, crat
cred | 相信 | 拉丁语 credere | cred
cresc, creas, cret | 增长 | 拉丁语 crescere | cresc
crit, cris | 判断 | 希腊语 krinein | krit, krin, kris, crit, cris
cruc | 十字 | 拉丁语 crux | cruc, crux
cub, cumb | 躺 | 拉丁语 cubare | cubare, cubat, cubit, cubicul, cumb, cubo
culp | 罪过 | 拉丁语 culpa | culp
cult | 耕种、培养 | 拉丁语 colere | cult
curr, curs, cour | 跑 | 拉丁语 currere | curr, curs
cur | 关心、照料 | 拉丁语 cura | cura, curi, curat
cycl | 圆、轮 | 希腊语 kyklos | kykl, cycl, kukl
deb | 欠 | 拉丁语 debere | deb
demo | 人民 | 希腊语 demos | demos, demo
dent | 牙齿 | 拉丁语 dens | dent, dens
dict, dic | 说 | 拉丁语 dicere | dicere, dico, dict, dicare, dicat
dign | 值得 | 拉丁语 dignus | dign
divid, divis | 分开 | 拉丁语 dividere | divid, divis
doct, doc | 教 | 拉丁语 docere | docere, doceo, doct, docil, docum
domin | 统治 | 拉丁语 dominus | domin
dom | 家 | 拉丁语 domus | domus, domest, domic
don | 给、赠 | 拉丁语 donare | donare, donat, donum
dorm | 睡 | 拉丁语 dormire | dorm
dox | 意见 | 希腊语 doxa | dox
duct, duc | 引导 | 拉丁语 ducere | ducere, duco, duct
dur | 持久、坚硬 | 拉丁语 durus | durus, durare, durat, durab
dynam | 力 | 希腊语 dynamis | dynam, dunam
eco | 家、环境 | 希腊语 oikos | oik
electr | 电 | 希腊语 elektron | elektr, electr
equ | 相等 | 拉丁语 aequus | aequ
err | 漫游、犯错 | 拉丁语 errare | errare, error, errat
fact, fect, fic, fac | 做 | 拉丁语 facere | facere, facio, fact, fect, ficere, ficio, ficare, fici, facil
fals, fall | 欺骗、错 | 拉丁语 fallere | fall, fals
fam | 说、名声 | 拉丁语 fama | fama, fari, fans, famos
femin | 女性 | 拉丁语 femina | femin
fend, fens | 打击 | 拉丁语 -fendere | fend, fens
fer | 带、拿 | 拉丁语 ferre | ferre, fero, ferens, ferent
fest | 节日 | 拉丁语 festus | fest
fict, fig | 塑造 | 拉丁语 fingere | fing, fict, figura
fid | 信任 | 拉丁语 fides | fid
fin | 结束、界限 | 拉丁语 finis | fin
firm | 坚固 | 拉丁语 firmus | firm
fix | 固定 | 拉丁语 figere | fix, figere
flam, flagr | 燃烧 | 拉丁语 flamma | flamm, flagr
flat | 吹 | 拉丁语 flare | flare, flat
flect, flex | 弯曲 | 拉丁语 flectere | flect, flex
flict | 打击 | 拉丁语 fligere | flig, flict
flor | 花 | 拉丁语 flos | flor, flos
flu, flux | 流 | 拉丁语 fluere | flu
form | 形状 | 拉丁语 forma | form
fort | 强 | 拉丁语 fortis | fort
fract, frag | 打破 | 拉丁语 frangere | frang, fract, frag
fug | 逃 | 拉丁语 fugere | fug
fund, found | 底部、基础 | 拉丁语 fundus | fundus, fundare, fundam
fus | 倾倒、熔 | 拉丁语 fundere | fus, fund
gen | 产生、种类 | 拉丁语 genus | gen, gign
geo | 地 | 希腊语 ge | geo
gest | 携带、进行 | 拉丁语 gerere | gest, gerere
glob | 球 | 拉丁语 globus | glob
gnos | 知道 | 希腊语 gnosis | gnos, gno
gon | 角 | 希腊语 gonia | gonia, gonos, gonon
grad, gress | 走、步、等级 | 拉丁语 gradus | grad, gress
graph, gram | 写、画 | 希腊语 graphein | graph, gramm
grand | 大 | 拉丁语 grandis | grand
grat | 感激、令人高兴 | 拉丁语 gratus | gratus, gratia, gratif, gratis, gratu, grat
grav | 重 | 拉丁语 gravis | grav
greg | 群 | 拉丁语 grex | greg, grex
hab, hib | 拥有、居住 | 拉丁语 habere | hab, hib
her, hes | 粘附 | 拉丁语 haerere | haer, haes
horr | 发抖、恐惧 | 拉丁语 horrere | horr
hosp, host | 客人、主人 | 拉丁语 hospes | hosp
hum | 土地、人 | 拉丁语 humus | humus, human, humil, humare
hydr | 水 | 希腊语 hydor | hydr, hudr
ide | 观念 | 希腊语 idea | idea
imag | 形象 | 拉丁语 imago | imag
insul, isol | 岛 | 拉丁语 insula | insul
integr | 完整 | 拉丁语 integer | integ
ject | 投、扔 | 拉丁语 jacere | jac, iac, ject, iect, jic, iic
journ | 日 | 拉丁语 diurnus | diurn
junct, join | 连接 | 拉丁语 jungere | iung, jung, iunct, junct
jur, jud, just | 法律、公正 | 拉丁语 jus | iud, jud, iur, jur, ius, jus
juven | 年轻 | 拉丁语 juvenis | iuven, juven
labor | 劳动 | 拉丁语 labor | labor
lax | 松 | 拉丁语 laxus | lax
lect | 选择、读 | 拉丁语 legere | lect, legere, lego
lev, liev | 轻、举起 | 拉丁语 levis | lev
liber | 自由 | 拉丁语 liber | liber
lig | 捆绑 | 拉丁语 ligare | ligare, ligat, ligo
limin, limit | 门槛、界限 | 拉丁语 limes | limit, limin, limes
lingu | 语言、舌 | 拉丁语 lingua | lingu
liqu | 液体 | 拉丁语 liquere | liqu
liter | 文字 | 拉丁语 littera | litter, liter
lith | 石 | 希腊语 lithos | lith
loc | 地方 | 拉丁语 locus | loc
log | 说话、学问 | 希腊语 logos | log
long | 长 | 拉丁语 longus | long
loqu, locut | 说 | 拉丁语 loqui | loqu, locut
luc, lumin, lustr | 光 | 拉丁语 lux | luc, lux, lumin, lustr
lud, lus | 玩、戏弄 | 拉丁语 ludere | lud, lus
magn | 大 | 拉丁语 magnus | magn
major | 较大 | 拉丁语 major | maior, major
mand, mend | 命令、委托 | 拉丁语 mandare | mand
manu, man | 手 | 拉丁语 manus | manu
mar | 海 | 拉丁语 mare | mare, marin, marit
mater, matr | 母亲 | 拉丁语 mater | mater, matr
matur | 成熟 | 拉丁语 maturus | matur
mechan | 机械 | 希腊语 mekhane | mekhan, mechan, machin
medic, med | 治疗 | 拉丁语 mederi | medic, mederi, remedi
medi | 中间 | 拉丁语 medius | medius, median, mediat, mediocr, medium, mediare
memor | 记忆 | 拉丁语 memor | memor
mens | 测量 | 拉丁语 metiri | mensur, mensus, mensio
merc | 贸易、报酬 | 拉丁语 merx | merc, merx
merg, mers | 沉、浸 | 拉丁语 mergere | merg, mers
metr, meter | 测量 | 希腊语 metron | metr
migr | 迁移 | 拉丁语 migrare | migr
milit | 士兵 | 拉丁语 miles | milit, miles
minist | 仆人、服务 | 拉丁语 minister | minist
min | 小 | 拉丁语 minor | minor, minus, minim, minu
mir | 惊奇、看 | 拉丁语 mirari | mir
misc, mix | 混合 | 拉丁语 miscere | misc, mixt
miss, mit | 送、放 | 拉丁语 mittere | mitt, miss
mob, mot, mov | 移动 | 拉丁语 movere | mov, mot, mobil
mod | 方式、尺度 | 拉丁语 modus | mod
monit, mon | 警告、提醒 | 拉丁语 monere | mone, moni, monu
moral | 习俗、道德 | 拉丁语 mos | moral, mores
morph | 形状 | 希腊语 morphe | morph
mort | 死 | 拉丁语 mors | mort, mors
mult | 多 | 拉丁语 multus | mult
mun | 公共、职责 | 拉丁语 munus | munis, munus, munic, muner, munio, munit
mur | 墙 | 拉丁语 murus | murus, mural, muralis, murare
mut | 改变 | 拉丁语 mutare | mut
narr | 讲述 | 拉丁语 narrare | narr
nat | 出生 | 拉丁语 nasci | nat, nasc
nav | 船 | 拉丁语 navis | nav
nect, nex | 连接 | 拉丁语 nectere | nect, nex
neg | 否认 | 拉丁语 negare | neg
neur | 神经 | 希腊语 neuron | neur
noc, nox | 伤害 | 拉丁语 nocere | noc, nox
noct | 夜 | 拉丁语 nox | noct
nomin | 名字 | 拉丁语 nomen | nomen, nomin
nom | 法则、管理 | 希腊语 nomos | nomos, nomia
norm | 规范 | 拉丁语 norma | norm
not | 标记、知道 | 拉丁语 nota | nota, notare, notus, notio, notit, notif
nov | 新 | 拉丁语 novus | nov
numer | 数 | 拉丁语 numerus | numer
nunci, nounc | 宣告 | 拉丁语 nuntiare | nunt, nunc
nutri, nutr | 滋养 | 拉丁语 nutrire | nutrire, nutrit, nutrix, nutrim
ocul | 眼 | 拉丁语 oculus | ocul
onym | 名字 | 希腊语 onoma | onym, onum, onom
oper | 工作 | 拉丁语 opus | oper, opus
opt, ops | 眼、看 | 希腊语 ops | optik, opsis, optos
ordin, ord | 秩序 | 拉丁语 ordo | ord
orig, ori | 升起、开始 | 拉丁语 oriri | orig, oriri, oriens, orient
orn | 装饰 | 拉丁语 ornare | orn
pac | 和平 | 拉丁语 pax | pax, pacis, pacif, pacat, pacare
pand, pans | 展开 | 拉丁语 pandere | pand, pans
part | 部分 | 拉丁语 pars | part, pars
pass, pati | 忍受、感受 | 拉丁语 pati | pati, passio, passiv, passib
path | 感受、痛苦 | 希腊语 pathos | path
patr, pater | 父亲 | 拉丁语 pater | pater, patr
ped | 脚 | 拉丁语 pes | ped
pel, puls | 推、驱 | 拉丁语 pellere | pell, puls
pend, pens | 悬挂、称量、支付 | 拉丁语 pendere | pend, pens
pen, pun | 惩罚 | 拉丁语 poena | poen, punire, punit, paenit, penal
pet | 追求、寻求 | 拉丁语 petere | pet
phen, phan | 显现 | 希腊语 phainein | phain, phan
phil | 爱 | 希腊语 philos | phil
phon | 声音 | 希腊语 phone | phon
phot | 光 | 希腊语 phos | phot, phos
phys | 自然、身体 | 希腊语 physis | phys, phus
pict | 画 | 拉丁语 pingere | ping, pict
plac, pleas | 使高兴、平静 | 拉丁语 placere | placere, placeo, placid, placat, placab, plaisir, plaire, placen
plain, plan | 平 | 拉丁语 planus | planus, planare, planum, planat
plaud, plod, plaus, plos | 鼓掌、爆发 | 拉丁语 plaudere | plaud, plod, plaus, plos
plen, plet, ple | 满 | 拉丁语 plere | plere, plen, plet, pleo
plic, plex, ply | 折叠 | 拉丁语 plicare | plic, plex, plect
plor | 哭喊 | 拉丁语 plorare | plor
plur, plus | 多 | 拉丁语 plus | plur, plus
pod | 脚 | 希腊语 pous | pod, pous
polit, polis, polic | 城邦、政治 | 希腊语 polis | polis, polit
pon, pos, posit, pound | 放置 | 拉丁语 ponere | pon, posit
popul, publ | 人民 | 拉丁语 populus | popul, publ
port | 携带；港口、门 | 拉丁语 portare | port
pot, poss | 能力 | 拉丁语 posse | potens, potent, posse, possib
preci, prec | 价值 | 拉丁语 pretium | preti
prehend, pris | 抓住 | 拉丁语 prehendere | prehend, prend, prens
press | 压 | 拉丁语 premere | prem, press
prim, princ | 第一 | 拉丁语 primus | prim, princ
priv | 私人、剥夺 | 拉丁语 privus | priv
prob, prov | 检验、证明 | 拉丁语 probare | prob
proper, propr | 自己的、适当 | 拉丁语 proprius | propri
proxim | 接近 | 拉丁语 proximus | proxim
psych | 心灵 | 希腊语 psyche | psych, psukh
pugn | 打斗 | 拉丁语 pugnare | pugn
punct, point | 点、刺 | 拉丁语 pungere | pung, punct
purg | 清洗 | 拉丁语 purgare | purg
pur | 纯净 | 拉丁语 purus | purus, purific, purit
put | 思考、计算 | 拉丁语 putare | putare, putat, puto
qual | 性质 | 拉丁语 qualis | qual
quant | 数量 | 拉丁语 quantus | quant
quest, quir, quis, quer | 寻求、询问 | 拉丁语 quaerere | quaer, quaes, quir, quis
quiet | 安静 | 拉丁语 quies | quiet, quies
radic | 根 | 拉丁语 radix | radic, radix
radi | 光线、辐射 | 拉丁语 radius | radi
ration, rat | 计算、理性 | 拉丁语 ratio | ratio, ration, ratus
rect, reg | 直、统治 | 拉丁语 regere | regere, rego, rect, regul, regio, regim
rid, ris | 笑 | 拉丁语 ridere | rid, risus, risio
rod, ros | 咬、侵蚀 | 拉丁语 rodere | rodere, rodo, rosio, rosus, rosiv
rog | 问、要求 | 拉丁语 rogare | rog
rot | 轮、转 | 拉丁语 rota | rota, rotund
rud | 粗糙 | 拉丁语 rudis | rud
rupt | 破裂 | 拉丁语 rumpere | rump, rupt
rur, rust | 乡村 | 拉丁语 rus | rur, rust
sacr, sanct | 神圣 | 拉丁语 sacer | sacr, sanct, sacer
salut, salv | 健康、安全 | 拉丁语 salus | salut, salv
san | 健康 | 拉丁语 sanus | sanus, sanit
satis, satur | 足够 | 拉丁语 satis | satis, satur
scend, scens | 攀爬 | 拉丁语 scandere | scand, scend, scens
schol | 学校、闲暇 | 希腊语 skhole | schol, skhol
sci | 知道 | 拉丁语 scire | scire, scio, scient, scius
scop | 看 | 希腊语 skopein | skop, scop
scrib, script | 写 | 拉丁语 scribere | scrib, script
sect, seg | 切 | 拉丁语 secare | secare, sect, segm
sed, sid, sess | 坐 | 拉丁语 sedere | sed, sid, sess
semin | 种子 | 拉丁语 semen | semin, semen
sens, sent | 感觉 | 拉丁语 sentire | sent, sens
sen | 老 | 拉丁语 senex | senex, senior, senat, senil
sequ, secut | 跟随 | 拉丁语 sequi | sequ, secut
sert | 加入、插入 | 拉丁语 serere | sert, serere
serv | 服务；保存 | 拉丁语 servire | serv
sign | 记号 | 拉丁语 signum | sign
simil, simul | 相似、一起 | 拉丁语 similis | simil, simul
sist | 站立 | 拉丁语 sistere | sist
soci | 同伴 | 拉丁语 socius | soci
solid | 坚固 | 拉丁语 solidus | solid
solv, solu | 松开、解决 | 拉丁语 solvere | solv, solut
somn | 睡 | 拉丁语 somnus | somn
son | 声音 | 拉丁语 sonus | sonus, sonare, sonan, sonor, sonit, sono
soph | 智慧 | 希腊语 sophos | soph
spect, spec, spic | 看 | 拉丁语 specere | spec, spic
spers | 散开 | 拉丁语 spargere | sparg, spars, spers
sper | 希望 | 拉丁语 sperare | sper
spher | 球 | 希腊语 sphaira | sphair, sphaer, spher
spir | 呼吸 | 拉丁语 spirare | spir
splend | 发光 | 拉丁语 splendere | splend
spond, spons | 承诺 | 拉丁语 spondere | spond, spons
stat, stit, stant, stanc, stabl | 站立 | 拉丁语 stare | stare, stat, stit, stant, stabil, sto
stell | 星 | 拉丁语 stella | stell
stimul | 刺激 | 拉丁语 stimulus | stimul
stinct, stingu | 刺、区分 | 拉丁语 stinguere | stingu, stinct
strict, strain, string | 拉紧 | 拉丁语 stringere | string, strict
struct, stru | 建造 | 拉丁语 struere | stru
stup | 惊呆 | 拉丁语 stupere | stup
suad, suas | 劝说 | 拉丁语 suadere | suad, suas
summ | 最高、总 | 拉丁语 summus | summus, summa, summare, summat
sumpt, sum | 拿、取 | 拉丁语 sumere | sumere, sumo, sumpt
surg, surrect | 升起 | 拉丁语 surgere | surg, surrect
tact, tang, ting, tag | 接触 | 拉丁语 tangere | tang, tact, ting
tain, tin, ten | 持、握 | 拉丁语 tenere | tene, tine
tard | 慢 | 拉丁语 tardus | tard
techn | 技艺 | 希腊语 tekhne | tekhn, techn
tect | 覆盖 | 拉丁语 tegere | teg, tect
temper | 调和 | 拉丁语 temperare | temper
tempor, temp | 时间 | 拉丁语 tempus | tempor, tempus
tempt | 尝试 | 拉丁语 temptare | tempt, tentare
tend, tens, tent | 伸展 | 拉丁语 tendere | tend, tens, tent
tenu | 细 | 拉丁语 tenuis | tenu
termin | 界限、结束 | 拉丁语 terminus | termin
terr | 土地 | 拉丁语 terra | terra, territ, terrest
terr | 恐吓 | 拉丁语 terrere | terrere, terror, terrib, terrif
test | 证明、见证 | 拉丁语 testis | test
text | 编织 | 拉丁语 texere | tex
theo | 神 | 希腊语 theos | theo
therm | 热 | 希腊语 thermos | therm
tim | 害怕 | 拉丁语 timere | tim
tom | 切 | 希腊语 tome | tome, tomos, tomia, temn
top | 地方 | 希腊语 topos | topos, topik, topia
tort | 扭曲 | 拉丁语 torquere | torqu, tort
tox | 毒 | 希腊语 toxikon | tox
tract | 拉 | 拉丁语 trahere | trah, tract
trem | 颤抖 | 拉丁语 tremere | trem
tribut, trib | 给予、分配 | 拉丁语 tribuere | tribu
trop | 转 | 希腊语 tropos | trop
trud, trus | 推 | 拉丁语 trudere | trud, trus
turb | 搅动 | 拉丁语 turba | turb
tut, tuit | 看护 | 拉丁语 tueri | tut, tuit, tueri
typ | 模型、印记 | 希腊语 typos | typ, tup
ultim | 最后 | 拉丁语 ultimus | ultim
umbr | 影 | 拉丁语 umbra | umbr
und, ound | 波浪、涌 | 拉丁语 unda | unda, undare, undans
urb | 城市 | 拉丁语 urbs | urb
util, us | 使用 | 拉丁语 uti | uti, usus, usu, util
vac | 空 | 拉丁语 vacare | vac
vad, vas | 走 | 拉丁语 vadere | vad, vas
vag | 漫游 | 拉丁语 vagari | vag
val, vail | 强、价值 | 拉丁语 valere | val
van | 空、消失 | 拉丁语 vanus | van
vari, var | 变化 | 拉丁语 varius | vari
vect, veh | 运载 | 拉丁语 vehere | veh, vect
ven, vent | 来 | 拉丁语 venire | veni, vent
verb | 词语 | 拉丁语 verbum | verb
verg | 倾向 | 拉丁语 vergere | verg
vert, vers | 转 | 拉丁语 vertere | vert, vers
ver | 真实 | 拉丁语 verus | verus, verit, verific, verax, verac
vest | 衣服 | 拉丁语 vestis | vest
vi | 路 | 拉丁语 via | via, vius, viam
vid, vis | 看 | 拉丁语 videre | vid, vis
vig, veg | 活力 | 拉丁语 vigere | vigere, vigor, vigil, vegetus, vegetare, vegetab
vinc, vict | 征服 | 拉丁语 vincere | vincere, vinco, vincibil, victor, victus, victori, convict, evict
virt, vir | 男人、力量 | 拉丁语 vir | virtu, viril
vit, viv | 生命、活 | 拉丁语 vita | vita, viv
voc, vok | 声音、叫 | 拉丁语 vox | voc, vox
volunt, vol | 意愿 | 拉丁语 voluntas | volunt, volens, volent
volv, volu | 卷、转 | 拉丁语 volvere | volv, volut, volum
vor | 吃 | 拉丁语 vorare | vor
vot | 誓言 | 拉丁语 votum | vot, vov
vulg | 普通人 | 拉丁语 vulgus | vulg
zo | 动物 | 希腊语 zoion | zoi, zoo
"""

# 前缀：标准写法 | 变体（后面括号里是变体后面必须跟的字母，没有括号 = 不限制）| 意思 | 语种（la 拉丁、grc 希腊、en 英语本族，决定能接哪种词根）
PREFIXES = """
ab | ab, abs(ct), a(pv) | 离开 | la
ad | ad, ac(cqk), af(f), ag(g), al(l), an(n), ap(p), ar(r), as(s), at(t), a(sg) | 向、加强 | la
ambi | ambi, amb | 两边、周围 | la
ante | ante | 在前 | la
bene | bene | 好 | la
bi | bi | 二 | la
circum | circum | 周围 | la
com | com(bmp), con, col(l), cor(r), co(aeiouh) | 共同、加强 | la
contra | contra, contro, counter | 相反 | la
de | de | 向下、离开、除去 | la
dis | dis, dif(f), di(glmrv) | 分开、否定 | la
en | en, em(bmp) | 使、进入 | la
ex | ex, ef(f), e(bdgjlmnrv) | 向外、出 | la
extra | extra | 之外 | la
in | in, im(bmp), il(l), ir(r) | 向内；不 | la
inter | inter | 之间 | la
intro | intro | 向内 | la
mal | mal, male | 坏 | la
multi | multi | 多 | la
non | non | 不 | la
ob | ob, oc(c), of(f), op(p), o(m) | 朝向、反对 | la
omni | omni | 全 | la
per | per | 穿过、彻底 | la
post | post | 在后 | la
pre | pre | 在前、预先 | la
pro | pro | 向前、支持 | la
re | re, red(aeiu) | 再、回 | la
retro | retro | 向后 | la
se | se | 分开 | la
semi | semi | 半 | la
sub | sub, suc(c), suf(f), sug(g), sum(m), sup(p), sus(cpt) | 在下 | la
super | super, sur | 在上、超过 | la
trans | trans, tran(s), tra(djv) | 穿过、转移 | la
tri | tri | 三 | la
ultra | ultra | 超 | la
uni | uni | 一 | la
a | a, an(aeiou) | 不、无 | grc
ana | ana | 向上、再 | grc
anti | anti, ant(aeiou) | 反对 | grc
apo | apo | 离开 | grc
auto | auto | 自己 | grc
cata | cata, cat(aeiou) | 向下 | grc
dia | dia | 穿过 | grc
dys | dys | 坏、困难 | grc
epi | epi | 在上、之后 | grc
eu | eu | 好 | grc
hemi | hemi | 半 | grc
hetero | hetero | 不同 | grc
homo | homo | 相同 | grc
hyper | hyper | 超过 | grc
hypo | hypo | 在下、不足 | grc
macro | macro | 大 | grc
micro | micro | 小 | grc
mono | mono | 单一 | grc
neo | neo | 新 | grc
ortho | ortho | 正、直 | grc
pan | pan | 全 | grc
para | para | 旁边、超出 | grc
peri | peri | 周围 | grc
poly | poly | 多 | grc
proto | proto | 第一 | grc
pseudo | pseudo | 假 | grc
syn | syn, sym(bmp), syl(l), sys(t) | 共同 | grc
tele | tele | 远 | grc
un | un | 不；相反动作 | en
mis | mis | 错误 | en
over | over | 过度、在上 | en
under | under | 不足、在下 | en
out | out | 向外、超过 | en
fore | fore | 在前、预先 | en
"""

# 后缀：写法 | 意思。也用来判断一个词去掉前缀和词根之后剩下的部分是不是“正常的词尾”
SUFFIXES = """
able, ible, ble | 能……的
al, ial, ual | ……的；动作
an, ian | ……的；……的人
ance, ence, ancy, ency | 状态、性质
ant, ent | ……的；做……的人或物
ar | ……的
ary, ory | ……的；场所、物
ate | 使……；……的
ation, ition, ion, tion, sion | 行为、状态、结果
ative, itive, ive | 有……性质的
ator, or, er, eer, ier | 做……的人或物
cle, cule, ule, acle, icle | 小东西；物
dom | 状态、领域
ee | 受……的人
en | 使……；……的
ess | 女性
ful | 充满……的
hood | 状态、身份
ic, ical, tic | ……的
ice | 性质、行为
id | ……的
ify, fy | 使……
ile | 易于……的
ine | ……的
ish | 像……的；使……
ism | 主义、行为
ist | ……者
ite | ……的；人
ity, ty | 性质、状态
ize, ise | 使……化
less | 没有……的
let | 小
ly | ……地；……的
ment | 行为、结果
ness | 性质、状态
ous, ious, eous, uous | 有……的
ship | 状态、身份
some | 易于……的
th | 状态、行为
tude, itude | 状态、性质
ure, ture | 行为、结果
ward | 向……
y | 性质、状态；……的
um, us, a, ia | 名词词尾
"""


def _rows(text: str):
    for line in text.strip().split("\n"):
        yield [c.strip() for c in line.split("|")]


def roots():
    out = []
    for forms, meaning, origin, stems in _rows(ROOTS):
        out.append({"forms": [f.strip() for f in forms.split(",")], "meaning": meaning, "origin": origin,
                    "lang": "grc" if origin.startswith("希腊") else "la", "stems": [s.strip() for s in stems.split(",")]})
    return out


def prefixes():
    out = []
    for canon, variants, meaning, lang in _rows(PREFIXES):
        forms = []
        for v in variants.split(","):
            v = v.strip()
            if "(" in v:
                forms.append((v[: v.index("(")], set(v[v.index("(") + 1: -1])))
            else:
                forms.append((v, None))
        out.append({"canon": canon, "forms": forms, "meaning": meaning, "lang": lang})
    return out


def suffixes():
    out = {}
    for forms, meaning in _rows(SUFFIXES):
        for f in forms.split(","):
            out[f.strip()] = meaning
    return out
