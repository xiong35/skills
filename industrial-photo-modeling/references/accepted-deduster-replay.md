# 已验收立环脉动除尘机 0.6.2：独立重建

仅在复现 v3_release_experiment 分支已验收除尘机、或研究它的可编辑实现时读取。该案例随 Skill 独立迁移，不表示 master 已接入除尘机业务或具有相应前端资源。新的设备仍走照片分析流程；本案例不是任意设备生成器，也不证明只凭两张原图能自动推断全部已确认细节。

## 同版输入与边界

`assets/ring-pulsating-deduster-v062/` 是来源分支已验收建模源的显式快照，不随业务自动同步。`source-snapshot.json` 记录来源提交、各源文件 SHA-256 与现用 GLB 指纹；`build_model.py`、`geometry.py`、`shading.py`、`parameters.json` 和 `reference-correspondence.json` 成套使用。`accepted-model.json`、`accepted-sensors.json` 是本设备已有清单与物理锚点验收基准，不是后端数据。

文本源指纹按 `hashNormalization: utf8-lf` 将 CRLF 统一为 LF 后计算，兼容 Git 跨系统的换行转换；GLB 的二进制指纹仍按原始字节计算。只允许换行差异，不忽略源代码或参数内容的改变。

本版本保留已确认的尾端 +X 出轴、短轴和联轴器、带深度与筋板的大圆壳体、开放式电机护盖、五孔带轮、三背盖间距、并列铸座/横台、完整平台以及青绿/钢灰材质。03/05 的已验收展示位置与其余七点保留。05/06 的现场名称、配对和真实传感器 ID 尚未核准，不能根据模型命名虚构。

尺寸为照片比例；材料和几何细节包含本项目已接受的人工解释。某些颜色、筋数及零件形状写在这台设备的源脚本中，并非每项都由 JSON 驱动。其他设备不能仅换 `typeKey`、照片或参数文件就宣称完成。后方圆壳体不旋转；生成的 `motion/running` 只是接入契约，包内没有前端卡片、报警、数据绑定或传动运行时。

## 实际重建

### 放到其他项目

整体复制 `industrial-photo-modeling/`，保留内部 `SKILL.md`、`scripts/`、`assets/`、`references/` 等相对位置；不能只复制 SKILL.md。文件夹可放在新项目中，也可放在项目外，调用脚本时指定实际位置即可。宿主是否自动发现该目录由宿主配置决定，显式读取该 Skill 或运行脚本不依赖自动发现。

复现只需要 Python 和带 glTF 导入/导出器的 Blender。当前实测组合是 Windows、Python 3.13、Blender 5.2.3 LTS；希望复现相同结果时优先用同版 Blender。无需原 Vue 项目、Node、后端、原始照片、原 GLB 或额外 pip 依赖。来源快照中的 `frontend/...` 路径仅记录出处，不会用于加载外部文件；Blender 可执行路径由本机显式提供。

执行入口会在 Blender 内明确关闭 Python 字节码写入，避免随建模在 Skill 源目录新增 `__pycache__`。所有模型、渲染、日志和临时运行配置放入本次新输出目录。

例如把文件夹放在目标项目 `.agents/skills/industrial-photo-modeling` 后，可从**目标项目根目录**执行以下命令；它按脚本自身位置查找资源，输出相对当前工作目录解析：

```powershell
python -X utf8 -B .agents/skills/industrial-photo-modeling/scripts/rebuild_deduster_case.py --blender '本机Blender可执行路径' --out 'generated/deduster-replay' --render --samples 32
```

需要复制这台设备的已验收效果时，使用包内材质、AO 和检查灯光，不根据目标项目的配色自动改模型。接入其他查看器后，页面灯光、曝光和色调映射仍需单独核对；该步骤与独立模型重建分开验证。新设备则重新分析资料，并按其目标项目要求建模。

### 从 Skill 目录运行

从 Skill 根目录执行，Python 使用标准库，Blender 用现有可执行文件；不安装软件。输出必须是 Skill 外的新目录，不能指定现有业务资源目录。封装入口核对源快照、隔离 Blender 用户配置、执行真实建模/导出/回读，保存日志、校验结果和产物：

```powershell
python -X utf8 -B scripts/rebuild_deduster_case.py --blender '你的Blender路径/blender.exe' --out '你的新输出目录/deduster-replay' --render --draft
```

`--draft` 为 1000×700 预览；去掉为 1600×1000。默认渲染正面、背面、背盖、侧法兰、圆壳体和电机局部，可用 `--shots front,rear` 限定；`--samples` 控制 Cycles 采样。源工程另存为可编辑 `.blend`，同时输出 GLB、manifest、sensors 和 QA。重建使用 `--bake-ao` 保留已验收的接触层次；不启用它会改变导出的明暗效果。

原几何配方自带的 `rear` 机位会裁到外侧圆壳体，因此执行入口额外使用 `scripts/render_deduster_rear.py` 生成 `rear-full.png`：按实际顶点拟合完整背面，验证全部顶点都在画幅内，保存相机与边界记录。它只修正检查构图，不改冻结几何或现有页面机位。其他局部图按其检查部位保留近景。

入口不读取旧 GLB，不复制旧 `.blend` 作为生成结果。已存在输出、缺 Blender、源文件被改动均以非零退出，不覆盖旧文件。案例修订时另行确定来源版本、更新快照和验收证据，不能只改哈希让测试通过。

## 如何判断“达到目前效果”

1. 先检查所有命令退出码、GLB 自包含和材质隔离、九点与现用清单的一致性；实际 Blender GLB 导入检查坐标往返。
2. 若可访问原项目，用现用 GLB 作只读基准，对照节点层级、变换、网格/索引/法线/UV/顶点色、材质和内嵌纹理。仅 GLB 文件大小、九点数量或源脚本相同不算外观等价。
3. 两份资产经同一个真实导入器，用相同灯光、相机、采样与色彩设置分别渲染，检查正反面和关键局部。JSON 排序、导出器元数据或很小的浮点舍入可能改变二进制哈希，应列出实际差异和预先设定的容差，不直接忽略。
4. 独立生成与旧资源复制、已确认配方复现与盲测照片建模、离线资产验证与前端监测分别报告。没有实测尺寸或新设备照片，不作对应保证。

已有实际验证的命令、版本、图像和差异报告留在该次交付中；此文档不继承旧验证结果。案例修订应保持同版文件集合，不能混用不同版本的同名文件。
