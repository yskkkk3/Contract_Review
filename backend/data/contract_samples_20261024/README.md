# 公开真实合同测试集（2026-10-24）

本目录收集自政府采购网及政府部门官网公开的已签订合同，仅用于本项目的文档解析、OCR、审阅、问答与合同比对测试。

| 文件 | 类型 | 合同名称 | 页数 | 文本层 | 公告来源 |
|---|---|---|---:|---|---|
| `01_物业管理服务合同.pdf` | 物业服务 | 河南省信访局2025年度物业管理服务项目 | 16 | 扫描 | [河南省政府采购网](https://zhumadian.zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=1724798) |
| `02_电子档案与人工智能系统升级合同.pdf` | 软件开发、AI、硬件集成 | 河南省档案馆电子档案接收管理系统及人工智能模块升级改造项目 | 9 | 有 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?infoId=2020067) |
| `03_医疗呼吸机设备采购合同.pdf` | 医疗设备采购 | 河南省中西医结合医院医疗设备购置计划包3合同 | 7 | 扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=2029051) |
| `04_实训楼建设工程监理合同.pdf` | 建设工程监理 | 河南护理职业学院实训楼项目监理合同 | 34 | 扫描 | [河南省政府采购网](https://erqi.zfcg.henan.gov.cn/henan/content?infoId=1992479) |
| `05_校区场地租赁合同.pdf` | 场地租赁 | 河南省工业学校租赁场地设立校区项目 | 8 | 扫描 | [河南省政府采购网](https://gongyi.zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=2021726) |
| `06_机关餐饮服务合同.pdf` | 餐饮服务 | 河南省政务大数据中心机关和政务服务大厅餐饮服务项目 | 7 | 扫描 | [河南省政府采购网](https://zhecheng.zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=1732262) |
| `07_特效影院影片版权租赁合同.pdf` | 版权许可、租赁 | 河南省科学技术馆特效影院影片播放权租赁项目 | 5 | 扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=1734059) |
| `08_农业保险遥感评价服务合同.pdf` | 遥感技术、保险评价服务 | 河南省财政厅农业保险遥感评价项目 | 9 | 扫描 | [河南省政府采购网](https://zhongyuan.zfcg.henan.gov.cn/henan/content?infoId=1826233) |
| `09_基建项目竣工结算评审框架协议.pdf` | 基建结算评审、框架协议 | 河南省财政厅基建项目竣工结（决）算评审服务项目 | 14 | 扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?bz=1&channelCode=H601401&infoId=2002655) |
| `10_建设项目前期咨询服务合同.pdf` | 工程前期咨询 | 河南财政金融学院产教融合实训基地等项目前期咨询项目 | 8 | 扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?bz=1&channelCode=H601401&infoId=1974113) |
| `11_医疗保障骨干网络运维合同.pdf` | 骨干网络运维 | 河南省医疗保障业务骨干网络运行维护项目 | 20 | 扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?bz=1&channelCode=H601401&infoId=2006691) |
| `12_训练比赛服装器材采购合同.pdf` | 体育服装器材采购 | 河南省重竞技航空运动中心专项训练比赛服装器材项目 | 9 | 基本为扫描 | [河南省政府采购网](https://zfcg.henan.gov.cn/henan/content?infoId=2031579) |
| `13_公路治超非现场执法系统采购合同.pdf` | 软硬件集成、工程、运维 | 三门峡市新建公路治超非现场执法系统项目 | 43 | 扫描 | [河南省政府采购网](https://zhengzhou.zfcg.henan.gov.cn/henan/content?channelCode=H601401&infoId=1988569) |
| `14_云安全运维服务合同.pdf` | 云安全运维 | 北京市智慧水务信息安全运维云安全服务项目 | 10 | 有 | [北京市水务局](https://swj.beijing.gov.cn/zwgk/zfcg/cghtgg/202602/t20260209_4503885.html) |

## 已完成验证

- 14 个文件均为有效 PDF，共 199 页。
- 文本型样本 `02`、`14` 已通过项目本地解析链。
- 扫描型样本 `03` 已通过 `qwen3.5-ocr` 云 OCR，两次解析均得到 9000 余字符，并识别到合同金额。
- `01`、`04`、`09`、`11`、`13` 超过当前 `OCR_MAX_PAGES=10` 的默认上限，适合测试长扫描合同截断与分批 OCR。

公开合同可能包含公告时已依法公开的联系人、签章等信息，请仅用于内部功能测试，不要再次公开分发或用于其他目的。
