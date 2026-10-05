from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT, WD_CELL_VERTICAL_ALIGNMENT, WD_ROW_HEIGHT_RULE
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.enum.style import WD_STYLE_TYPE
from pathlib import Path

OUT = Path('铅笔制造AI-BOM智能体整体实施方案.docx')
doc = Document()
sec = doc.sections[0]
sec.top_margin = Inches(0.65)
sec.bottom_margin = Inches(0.65)
sec.left_margin = Inches(0.75)
sec.right_margin = Inches(0.75)

styles = doc.styles
styles['Normal'].font.name = 'Microsoft YaHei'
styles['Normal']._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
styles['Normal'].font.size = Pt(10.5)
for name, size, color in [('Title', 22, '17365D'), ('Heading 1', 16, '17365D'), ('Heading 2', 12.5, '2F5597'), ('Heading 3', 11, '404040')]:
    st = styles[name]
    st.font.name = 'Microsoft YaHei'
    st._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    st.font.size = Pt(size)
    st.font.bold = True
    st.font.color.rgb = RGBColor.from_string(color)

# custom compact style
if 'Table Text' not in styles:
    st = styles.add_style('Table Text', WD_STYLE_TYPE.PARAGRAPH)
    st.font.name = 'Microsoft YaHei'
    st._element.rPr.rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
    st.font.size = Pt(9)

def shade(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    for old in tcPr.findall(qn('w:shd')):
        tcPr.remove(old)
    shd = OxmlElement('w:shd')
    shd.set(qn('w:fill'), fill)
    tcPr.append(shd)

def set_cell_margins(cell, top=80, start=100, bottom=80, end=100):
    tcPr = cell._tc.get_or_add_tcPr()
    tcMar = tcPr.first_child_found_in('w:tcMar')
    if tcMar is None:
        tcMar = OxmlElement('w:tcMar')
        tcPr.append(tcMar)
    for side, value in [('top', top), ('start', start), ('bottom', bottom), ('end', end)]:
        node = tcMar.find(qn(f'w:{side}'))
        if node is None:
            node = OxmlElement(f'w:{side}')
            tcMar.append(node)
        node.set(qn('w:w'), str(value))
        node.set(qn('w:type'), 'dxa')

def set_cell_text(cell, text, bold=False, color=None, alignment=WD_ALIGN_PARAGRAPH.LEFT):
    cell.text = ''
    p = cell.paragraphs[0]
    p.style = 'Table Text'
    p.alignment = alignment
    p.paragraph_format.space_before = Pt(0)
    p.paragraph_format.space_after = Pt(0)
    r = p.add_run(str(text))
    r.bold = bold
    if color:
        r.font.color.rgb = RGBColor.from_string(color)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    set_cell_margins(cell)

def set_table_borders(t, color='B7C9D6', size='6'):
    tblPr = t._tbl.tblPr
    borders = tblPr.first_child_found_in('w:tblBorders')
    if borders is None:
        borders = OxmlElement('w:tblBorders')
        tblPr.append(borders)
    for edge in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        node = borders.find(qn(f'w:{edge}'))
        if node is None:
            node = OxmlElement(f'w:{edge}')
            borders.append(node)
        node.set(qn('w:val'), 'single')
        node.set(qn('w:sz'), size)
        node.set(qn('w:space'), '0')
        node.set(qn('w:color'), color)

def set_fixed_layout(t):
    tblPr = t._tbl.tblPr
    layout = tblPr.first_child_found_in('w:tblLayout')
    if layout is None:
        layout = OxmlElement('w:tblLayout')
        tblPr.append(layout)
    layout.set(qn('w:type'), 'fixed')

def table(headers, rows, widths=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.style = 'Table Grid'
    set_fixed_layout(t)
    set_table_borders(t)
    short_headers = {'人天', '对应人天', '数量', '周期', '等级', '金额（元）', '固定金额（元）', '参考金额（元）', '参考单价（元/天）'}
    for i, h in enumerate(headers):
        align = WD_ALIGN_PARAGRAPH.CENTER
        set_cell_text(t.rows[0].cells[i], h, True, 'FFFFFF', align)
        shade(t.rows[0].cells[i], '1F4E78')
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row[:len(headers)]):
            align = WD_ALIGN_PARAGRAPH.CENTER if headers[i] in short_headers else WD_ALIGN_PARAGRAPH.LEFT
            set_cell_text(cells[i], val, alignment=align)
            if len(t.rows) % 2 == 0:
                shade(cells[i], 'F3F6FA')
    if widths:
        for row in t.rows:
            for i, w in enumerate(widths[:len(headers)]):
                row.cells[i].width = Inches(w)
    for row in t.rows:
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row.height = Pt(22)
    doc.add_paragraph().paragraph_format.space_after = Pt(0)
    return t

def bullet(text, level=0):
    p = doc.add_paragraph(style='List Bullet' if level == 0 else 'List Bullet 2')
    p.paragraph_format.space_after = Pt(2)
    p.add_run(text)
    return p

def para(text='', bold_prefix=None):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(4)
    if bold_prefix and text.startswith(bold_prefix):
        p.add_run(bold_prefix).bold = True
        p.add_run(text[len(bold_prefix):])
    else:
        p.add_run(text)
    return p

def note(text):
    p = doc.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.15)
    p.paragraph_format.space_after = Pt(4)
    r = p.add_run('说明：' + text)
    r.italic = True
    r.font.color.rgb = RGBColor.from_string('666666')
    return p

# Cover
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(65)
r = p.add_run('铅笔制造\nAI-BOM智能体整体实施方案')
r.bold = True
r.font.size = Pt(24)
r.font.color.rgb = RGBColor.from_string('17365D')
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(18)
r = p.add_run('基于招标文件《铅笔制造AIBOM.docx》编制')
r.font.size = Pt(12)
r.font.color.rgb = RGBColor.from_string('666666')
p = doc.add_paragraph()
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_before = Pt(105)
r = p.add_run('版本：V1.0    |    日期：2026年9月16日')
r.font.size = Pt(10)
r.font.color.rgb = RGBColor.from_string('777777')
doc.add_page_break()

# Executive summary
doc.add_heading('一、项目理解与实施结论', level=1)
para('本项目面向铅笔制造企业多色号、多规格、辅料差异化订单的 BOM 编制场景，建设一套部署在客户内网的 AI-BOM 智能体。系统从订单文档中识别产品规格、色号、数量、包装及辅料等字段，结合经过确认的历史 BOM 和物料规则，生成可追溯的 EBOM 草稿，并支持同类订单按色号/辅料批量派生、人工校核、版本留痕和结果导出。')
para('实施结论：在客户提供服务器及运行环境、样例订单、符合导入模板的历史 BOM 原始资料，并安排业务骨干参与规则确认的前提下，首期受限范围 MVP 建议投入约 34 人天，采用 10 周实施节奏：第 1-7 周完成开发与核心联调，第 8-9 周完成测试和问题闭环，第 10 周完成生产部署指导、培训及试运行；核心可用版本可在第 6 周完成测试环境演示。首期实施总预算为人民币 70,000 元（未税）。')
note('70,000 元对应受限范围 MVP：首期支持不超过 2 种已确认订单模板、单一产品系列、低并发使用和约定格式的文本型 DOCX/XLSX/PDF；不包含服务器、GPU、操作系统、中间件、模型软件授权、模型调用/API/Token/推理服务费用，也不包含历史 BOM 全量清洗标准化、ERP/MES 接口、扫描件 OCR 专项治理、复杂审批流、高可用集群和新增业务模块。若原始资料质量或范围超出前述边界，应在需求确认后另行核定数据治理、接口及基础设施相关费用。')

doc.add_heading('二、首期人天估算（先行估算）', level=1)
table(['工作包','主要工作内容','角色配置','人天','交付结果'], [
('1.需求调研与范围确认','订单样本盘点、BOM字段/模板确认、业务规则访谈、验收用例固化','项目经理/产品经理','4','需求规格说明书、字段字典、验收用例'),
('2.总体架构与安全设计','智能体分层、数据流、权限、审计、部署拓扑、备份恢复设计','架构师/项目经理','2','总体设计、部署架构、安全方案'),
('3.数据接入与知识库初始化','导入模板、数据质量检查、分类分层、样例整理、索引构建；不含全量清洗和编码重构','数据/知识工程师','5','知识库初始版本、导入脚本、数据质量清单'),
('4.订单文档解析','DOCX/XLSX/PDF文本解析、表格识别、字段抽取、异常提示、解析结果确认','AI/后端工程师','6','订单解析流程及接口'),
('5.EBOM推导与规则引擎','物料映射、层级生成、单位/用量校验、规则优先级、来源引用、低置信度拦截','AI/后端工程师','7','EBOM生成服务、规则配置'),
('6.差异订单批量生成','基准订单选择、色号/辅料差异识别、批量任务、任务重试、结果校验','后端工程师','3','批量生成模块'),
('7.结果工作台','BOM预览、人工编辑、差异对比、版本记录、查询、导出','前后端工程师','4','BOM工作台与记录查询'),
('8.私有化部署与测试','容器编排、环境配置、日志监控、功能/准确性/性能测试、修复回归','DevOps/测试工程师','2','测试报告、部署包、配置手册'),
('9.上线指导与培训','生产部署指导、试运行陪跑、远程培训、手册编制、验收支持','项目经理/实施工程师','1','操作手册、培训记录、验收资料'),
('合计','','','34','')], [1.55, 3.0, 1.25, 0.48, 1.6])
para('建议团队：项目经理/产品、AI/知识工程师、后端工程师、前端工程师及 DevOps/测试按阶段兼职投入。以上为阶段性并行角色投入，不等于连续 34 个工作日；计划周期约 10 周，依赖客户按期提供环境、样本并完成规则确认。')
para('建议首期导入上限：不超过 800 条已具备物料编码和父子层级的 BOM 记录、300 条物料主数据、2 种订单模板、20 份验收订单样本；超过上限或存在大量重复、缺失、版本冲突时，在数据画像完成后重新估算。客户负责原始资料完整性和业务确认，服务商负责受限范围内的导入、校验及问题报告。')

doc.add_heading('2.1 人天估算前提与调整项', level=2)
for x in [
'客户提供至少 20 份具有代表性的订单样本，覆盖单色、多色、规格变化、辅料变化、异常字段等场景；提供历史 BOM 原始文件及字段说明。',
'首期输入以可复制文本的 DOCX/XLSX 及含文本层的 PDF 为主；PDF 仅支持文本层解析。若大量资料为低清扫描件、手写单据或图片，需增加 OCR 评估与数据治理工作包。',
'首期输出为 EBOM 草稿和可导出的结构化文件，最终下单/生产前由业务人员确认；系统不直接替代工程/采购审批。',
'不做 ERP/MES/PLM 对接，不建设复杂审批流，不承诺未经标注的历史资料自动达到生产级准确率。',
'人天可按数据规模调整：历史 BOM 超过 800 条、物料主数据超过 300 条、订单模板超过 2 种或新增 ERP 接口时，在需求确认阶段重新估算。']:
    bullet(x)

# Architecture
doc.add_heading('三、智能体整体架构', level=1)
para('采用“文档解析层 + 业务编排层 + 规则/知识层 + 人机协同层”的四层业务架构，并由基础设施层提供运行支撑。大模型负责自然语言理解、字段抽取、候选匹配和解释；确定性的物料编码、用量计算、层级校验和差异派生由规则引擎执行，避免把关键 BOM 计算完全交给大模型。')
table(['层级','核心组件','职责','关键控制'], [
('交互层','Web上传/工作台、任务中心、BOM预览编辑','上传订单、查看解析、确认/修正 BOM、查询历史','权限控制、文件类型/大小限制、操作留痕'),
('智能编排层','Router、订单解析Agent、BOM生成Agent、批量派生Workflow','按任务类型编排解析、检索、匹配、校验和人工确认','固定流程优先；异常转人工；结构化输出'),
('业务服务层','文档服务、BOM服务、规则服务、批处理服务、导出服务','管理任务、版本、物料映射、差异计算、导出','幂等、重试、事务、版本号、审计日志'),
('知识与数据层','BOM知识库、物料主数据、规则库、向量索引、关系数据','提供历史案例、物料属性、替代关系、工艺约束和来源证据','数据版本、有效期、来源、审核状态、可追溯引用'),
('基础设施层','内网网关、应用容器、数据库、对象存储、日志监控','提供私有化运行、备份、恢复和运维能力','最小权限、网络隔离、备份演练、健康检查')], [1.0, 2.0, 3.1, 1.65])

doc.add_heading('3.1 智能体工作流', level=2)
for x in [
'接收订单：校验文件扩展名、MIME 类型、大小和模板版本，生成任务 ID；如客户要求病毒扫描，依赖客户提供或另行采购的安全组件。',
'文档解析：识别表格/段落，抽取订单号、产品系列、规格、色号、数量、包装、辅料和特殊要求；无法识别的字段标记为“待确认”。',
'结构化校验：按字段类型、枚举值、单位、必填项和互斥规则进行校验；不通过则返回修正清单。',
'知识检索：先按物料编码、产品系列、色号、规则条件进行精确/关键词检索，再用向量检索补充相似历史案例；返回带来源的候选证据。',
'EBOM生成：规则引擎确定层级、物料编码和用量，大模型仅处理语义映射与解释；对无匹配或多候选场景输出候选列表，不擅自选定。',
'批量派生：选择已确认的基准 BOM，仅替换允许变更的色号/辅料字段，校验不可变字段和物料组合约束，形成批量任务。',
'人工确认：按置信度分级展示；业务人员可编辑、驳回、确认，系统保存修改前后差异和操作者。',
'输出与沉淀：首期以双方确认的 XLSX 模板作为唯一主输出格式；如确认需要，再增加 CSV 导出。经确认的修正记录进入待审核知识增量，不直接自动写入生产知识库。']:
    bullet(x)

doc.add_heading('3.2 可信输出机制', level=2)
table(['场景','系统行为','业务人员动作'], [
('高置信度且规则通过','展示建议 BOM、来源和校验结果','抽查后确认'),
('存在多个候选物料','展示候选物料及差异，不自动落单','选择正确物料并确认'),
('缺失必填字段/规则冲突','阻断生成或生成“待确认”草稿','补充字段或修正规则'),
('历史案例与当前订单不一致','提示案例适用条件和时间，不直接复制','确认适用范围'),
('模型/服务异常','保留任务状态，可重试，不丢失原始文件','重试或转人工处理')], [1.7, 3.3, 2.8])

# KB
doc.add_heading('四、BOM知识库构建思路', level=1)
para('知识库不采用“把所有历史 BOM 直接向量化”的做法，而是建立可计算的结构化主数据、可检索的业务文档和可执行的规则三类资产。三者通过产品系列、物料编码、色号、版本和适用条件关联。')
table(['知识资产','建议内容','存储/检索方式','首期建设方法'], [
('物料主数据','物料编码、名称、类别、规格、单位、颜色/色号、包装、状态、替代料','关系库精确查询 + 同义词表','客户提供原始表；共同确认字段和唯一键'),
('BOM结构库','父项/子项、层级、基准用量、损耗、版本、生效期、适用产品','关系库/结构化JSON；按条件过滤','导入已确认历史 BOM，保留来源文件和版本'),
('规则库','色号替换规则、辅料组合、必选/互斥、用量计算、异常阈值','规则表 + 可配置规则服务','业务访谈固化为可测试规则'),
('历史案例库','订单条件、最终 BOM、异常原因、人工修正、适用边界','全文/向量混合检索 + 重排序','只纳入审核通过案例，标记适用条件'),
('模板与术语库','订单模板、字段别名、单位换算、颜色别名、供应商名称别名','关键词/字典匹配','建立字段字典和同义词表'),
('操作与工艺文档','包装规范、检验要求、特殊说明','文档切分 + 向量检索','按章节切分并绑定产品范围')], [1.35, 2.9, 2.0, 1.55])

doc.add_heading('4.1 数据治理流程', level=2)
for x in [
'资料盘点：统计文件类型、记录数量、字段完整率、重复率、版本冲突和缺失编码。',
'标准建模：确认物料编码唯一性、父子层级、单位、色号字典、辅料分类和状态字段。',
'导入校验：按必填、类型、引用完整性、重复主键和层级闭环校验，输出问题清单。',
'业务确认：由采购/工程/生产代表确认基准 BOM、替代料和颜色/辅料变更边界。',
'索引构建：结构化字段用于过滤，文本用于关键词和向量检索；检索结果必须返回来源和版本。',
'持续闭环：人工修正先进入审核队列，审核通过后按版本发布；每次发布可回滚。']:
    bullet(x)
note('招标文件明确“不包含历史 BOM 原始数据的清洗、标准化工作”。本方案的人天仅覆盖导入模板、质量检查、少量样例整理和知识库初始化；若客户希望服务商承担全量清洗，应单独报价。')

doc.add_heading('4.2 知识库验收建议', level=2)
table(['指标','建议首期目标','说明'], [
('字段抽取准确率','代表性样本关键字段 ≥ 90%','按订单号、规格、色号、数量、辅料等字段分别统计'),
('BOM结构完整率','已确认基准样本 ≥ 95%','父子层级、物料编码、单位、用量字段完整'),
('规则命中率','已固化规则场景 ≥ 95%','规则覆盖范围内的样本统计'),
('可追溯性','100%','每个建议物料可定位到规则、主数据或历史案例来源'),
('人工修正可留痕','100%','记录原值、新值、操作者、时间、原因和版本')], [1.8, 1.7, 4.3])

# Deployment
doc.add_heading('五、私有化部署方案', level=1)
para('采用客户内网部署为主、单机 Docker Compose 起步的方案。首期不依赖外部业务系统，降低网络和集成风险；单机模式仅提供容器隔离和基础备份，不等同于高可用集群，批量并发和故障切换能力以需求确认后的容量测试结果为准。后续如接入 ERP/MES，可在现有业务服务层增加适配器，不改变智能体核心流程。')
table(['组件','首期建议','用途'], [
('应用服务','AI-BOM API、任务服务、规则服务、导出服务、Web前端','业务功能与智能体编排'),
('模型服务','客户批准的本地大模型推理服务；或部署在客户认可的内网模型网关','解析、语义匹配、解释生成'),
('知识检索','PostgreSQL + 向量扩展作为首选；若数据规模或并发验证有需要，再启用独立向量数据库','结构化条件过滤与相似检索'),
('文件存储','内网对象存储或受控文件目录','订单原件、导出文件、版本附件'),
('缓存/队列','Redis（可选）+ 任务队列','批量任务状态、重试和并发控制'),
('运维','Nginx、容器健康检查、集中日志、备份脚本','访问控制、监控和恢复')], [1.45, 3.55, 2.8])

doc.add_heading('5.1 环境与硬件建议', level=2)
table(['配置档位','建议配置','适用范围'], [
('测试环境','客户提供的可用内网主机；8核 CPU、32GB内存、500GB SSD；无GPU也可验证流程','需求确认、功能测试、少量样本'),
('生产基础配置','客户提供的可用内网主机；16核 CPU、64GB内存、1TB SSD；GPU按客户批准的模型路线另行提供','单团队使用、低并发批量生成'),
('生产推荐配置','客户按模型要求提供计算、存储和备份资源；建议24-32核 CPU、128GB内存、2TB SSD，并按模型要求配置 GPU','订单高峰、较大知识库、稳定试运行')], [1.5, 3.8, 2.5])
para('实际硬件由客户提供，且不计入本项目 70,000 元实施总价；需在需求阶段依据模型参数量、并发数、单日订单量和保留周期复核。GPU、服务器、操作系统、中间件、存储及备份资源，以及大模型软件授权和模型调用/API/Token/推理服务费用均由客户提供或另行承担。若客户暂无 GPU，建议先采用轻量模型完成解析与检索验证，复杂推理通过客户认可的内网模型服务提供，避免在没有硬件依据时承诺本地大模型性能。')

doc.add_heading('5.2 安全与运维措施', level=2)
for x in [
'网络隔离：首期单机通过容器网络和端口白名单实施逻辑隔离；生产环境禁止数据库直接暴露。如客户要求应用、数据库和模型服务跨主机或安全域部署，需提供相应服务器与网络条件并另行评估。',
'身份权限：管理员、工程/采购、普通操作员、只读审计等角色分权；上传、编辑、确认、发布分别授权。',
'数据保护：订单原件、BOM和日志存储在客户内网；传输采用 HTTPS/内网 TLS；日志对敏感字段脱敏。',
'审计追溯：记录原始文件哈希、解析版本、知识库版本、模型版本、规则版本、人工修正和导出记录。',
'备份恢复：数据库每日增量、每周全量；文件按策略备份；上线前完成一次恢复演练。',
'模型治理：模型不可用时保留任务并支持重试；模型输出必须经过 schema 校验和规则校验，禁止直接写入主数据。']:
    bullet(x)

# Implementation
doc.add_heading('六、项目实施计划（10周）', level=1)
table(['阶段','周期','主要活动','里程碑/产出'], [
('启动与需求确认','第1周','样本收集、流程访谈、字段/模板/规则确认、验收指标确认','需求规格说明书 V1、样本清单、验收用例'),
('架构与数据准备','第2周','部署基线、数据模型、导入模板、知识分类、解析方案设计','架构设计、字段字典、数据质量报告'),
('订单解析开发','第3-4周','文档解析、字段抽取、校验、任务管理、异常提示','解析流程可演示'),
('EBOM与知识库开发','第4-6周','知识库导入、检索、规则引擎、EBOM生成、来源追溯','核心功能演示版本'),
('批量与工作台开发','第6-7周','差异识别、批量任务、预览编辑、版本查询、导出','完整测试版本'),
('联调与效果调优','第8周','样本回放、规则修正、异常场景、权限和日志验证','测试报告初稿'),
('部署与验收测试','第9周','测试环境部署、功能/性能/安全检查、问题闭环','验收候选版本、部署手册'),
('生产指导与试运行','第10周','生产部署指导、远程培训、试运行陪跑、验收确认','生产部署包、操作手册、验收资料')], [1.35, 1.0, 3.8, 2.0])
note('第3-7周可并行开展后端、知识库和前端工作。若客户无法按期提供样本或规则确认，里程碑顺延；模型/服务器采购不计入上述开发周期。')

# Functional response
doc.add_heading('七、功能需求逐条响应', level=1)
table(['招标功能','响应方式','定制工作量（已含在34人天/70,000元内）','验收关注点'], [
('订单文档智能解析','支持上传约定格式的 DOCX/XLSX 及含文本层的 PDF；抽取规格、色号、辅料等字段，提供解析结果确认和异常清单。扫描件、图片和手写文档 OCR 另行评估','订单解析 6人天','代表性样本字段准确、异常可定位'),
('EBOM自动推导生成','结构化字段检索物料主数据和历史 BOM，结合规则引擎生成层级 BOM；显示来源、版本和置信度','知识库与规则 12人天','结构完整、物料可追溯、规则冲突可拦截'),
('差异化订单BOM批量生成','选择基准 BOM，配置允许变化的色号/辅料，批量创建任务并逐条校验；失败任务可重试','批量生成 3人天','批量结果不串单、不丢失、差异可对比'),
('BOM结果处理','支持预览、编辑、差异对比、确认/驳回、版本记录、查询和约定模板导出','工作台 4人天','人工修改留痕、记录可查、导出字段正确'),
('私有化与交付','内网容器部署、配置手册、用户手册、测试报告、部署指导和远程支持','部署测试培训 5人天','业务数据隔离、服务可启动、交付物完整')], [1.55, 3.5, 1.25, 1.85])

doc.add_heading('7.1 招标要求逐条响应矩阵', level=2)
table(['招标要求','响应结论','对应章节/交付物'], [
('智能体整体架构','满足；采用四层业务架构+基础设施支撑，固定流程由Workflow编排，语义任务由Agent处理','第三章、总体设计文档'),
('私有化部署方案','满足；首期客户内网容器化部署，模型服务按客户批准路线实施','第五章、部署包、配置手册'),
('BOM知识库构建思路','满足；建设主数据、BOM结构、规则、案例和术语资产，并保留来源版本','第四章、知识库初始数据'),
('订单解析、EBOM、批量生成、结果处理','满足；逐项实现并提供人工确认、异常拦截和任务留痕','第七章、测试报告'),
('历史BOM知识库能力','满足受限范围；客户提供符合模板的原始资料，服务商负责导入、校验和初始索引','第四章、数据质量清单'),
('测试环境部署及生产部署指导','满足；提供测试部署、生产部署指导、环境检查和故障排查手册','第五章、第十章'),
('需求文档、部署手册、用户手册、测试报告','满足；纳入正式交付物清单','第十章、交付物清单'),
('项目实施计划及分项报价','满足；提供10周计划、34人天及70,000元费用测算','第六章、9.3节'),
('相关案例','如投标方具备同类案例，应在正式投标文件中补充可核验案例；本实施方案不虚构案例','第十二章'),
('售后运维方案','满足；按P1-P4分级响应，质保期内远程支持和Bug闭环','第十章、9.4节')], [2.25, 3.6, 1.85])

doc.add_heading('7.2 业务目标“效率提升2倍”的测量方法', level=2)
para('项目启动时由甲方选取不少于 20 份代表性订单，记录人工从接收订单到形成可确认 BOM 的平均有效工时，形成上线前基线。试运行阶段使用同类订单，记录系统解析、人工修正、确认和导出全流程有效工时，剔除等待客户补充资料的时间。以“基线平均工时 ÷ 上线后平均工时”计算效率倍数；建议将“达到 2 倍”作为持续改进目标，首期验收先以样本准确性、流程可用性和人工修正时间下降为硬性验收项。')

# Acceptance
doc.add_heading('八、验收方案', level=1)
para('验收以双方在需求确认阶段签字固化的样本集和用例为准。建议使用“基准样本 + 差异样本 + 异常样本”三组数据，避免只用演示数据验收。')
table(['验收类别','建议用例','通过条件'], [
('功能验收','上传订单、解析字段、生成 EBOM、批量派生、人工编辑、查询和导出','招标功能全部可操作；错误有提示；记录可追溯'),
('准确性验收','不少于 20 份代表性订单，覆盖多色号和辅料差异','关键字段、结构和规则指标达到确认目标；不确定场景不乱填'),
('批量稳定性','一次提交多条同类差异订单，包含重复和异常任务','任务状态准确；成功/失败可区分；无串单、丢单；失败可重试'),
('安全验收','角色权限、日志、备份恢复、内网访问检查','越权操作被拒；数据不出客户边界；可恢复关键数据'),
('交付验收','程序包、配置手册、操作手册、测试报告、验收模板','交付物齐全，客户可按手册完成启动和基本操作')], [1.25, 3.45, 3.0])

# Scope, risks, price estimate
doc.add_heading('九、范围边界、风险与报价建议', level=1)
doc.add_heading('9.1 范围边界', level=2)
table(['包含','不包含/需另行确认'], [
('AI-BOM智能体、订单解析、EBOM生成、差异订单批量生成、结果编辑查询','历史 BOM 全量清洗、编码重构、重复数据治理'),
('历史 BOM 知识库架构、导入模板、初始导入指导和检索调优','ERP、MES、PLM、财务或生产系统接口'),
('测试环境部署、生产环境部署指导、远程培训和3个月质保','线下驻场培训、7×24运维；服务器、GPU、操作系统、中间件、存储等基础设施费用；模型软件授权及模型调用/API/Token/推理服务费用'),
('约定格式文档解析和结构化导出','大量扫描/手写文档 OCR 专项、复杂版式定制')], [3.65, 3.65])
doc.add_heading('9.2 主要风险与应对', level=2)
for x in [
'数据质量风险：历史 BOM 字段缺失、同名异物、版本混用会直接影响生成质量。应在第1-2周完成数据画像和问题清单，将不可用资料隔离。',
'规则隐性风险：色号和辅料替换可能存在未文档化经验。应让业务专家参与规则确认，所有规则配置可查看、可测试、可回滚。',
'模型不确定性：大模型可能产生看似合理但错误的物料。应采用结构化输出、检索来源、规则校验和低置信度人工确认四道控制。',
'上线节奏风险：客户无 IT 团队。服务商应提供一键部署包、环境检查脚本、故障排查手册和远程陪跑；客户至少指定一名系统联系人和两名业务管理员。',
'硬件风险：本地模型性能取决于 GPU 和模型规格。项目启动前需锁定模型路线和服务器配置，否则只承诺流程可用，不承诺固定响应时延。']:
    bullet(x)

doc.add_heading('9.3 受限范围 MVP 固定总价测算（参考）', level=2)
table(['费用项','对应人天','固定金额（元）','说明'], [
('需求与方案','6','8,000','需求确认、字段字典、架构与安全方案'),
('订单解析与字段校验','6','16,000','约定模板解析、字段抽取、结构化校验与异常提示'),
('知识库初始化、检索与规则/EBOM推导','12','22,000','受限数据导入、检索、规则配置和 EBOM 草稿生成'),
('差异批量生成与结果工作台','7','12,000','基准派生、批量任务、预览编辑、差异对比和版本留痕'),
('部署、测试、培训与质保交付','2','8,000','测试部署、生产部署指导、手册、培训和3个月远程质保'),
('项目协调与风险预留','','4,000','项目协调、问题闭环和小范围返工预留'),
('首期实施固定总价','34','70,000','未含税；税率按合同约定')], [2.55, 0.8, 1.25, 3.0])
para('报价口径：首期实施固定总价为人民币 70,000 元（未税）。服务器、GPU、操作系统、中间件、存储等基础设施采购和扩容费用，以及大模型软件授权、模型调用/API/Token/推理服务费用，均不包含在上述总价内，由客户提供或另行承担；历史 BOM 全量清洗、扫描件 OCR、ERP/MES/PLM 接口、驻场服务和 7×24 运维等超出范围事项另行评估报价。')

doc.add_heading('9.4 售后运维与 Bug 修复机制', level=2)
table(['等级','典型情形','首次响应','临时恢复/绕行','修复与闭环'], [
('P1 紧急','系统无法启动、数据丢失/串单、核心生成流程全面不可用','工作日4小时内；重大故障按双方约定的紧急渠道即时通知','启动专项处理，持续跟踪并提供人工绕行方案，目标24小时内恢复核心服务','定位后优先发布修复；完成回归测试、变更记录和双方确认后关闭'),
('P2 高','核心功能明显受影响，但有替代操作；批量任务失败率异常','1个工作日内','提供临时配置或操作绕行，目标2个工作日内恢复主要功能','一般在5个工作日内提供修复版本或明确计划'),
('P3 一般','非核心功能缺陷、页面显示或单一规则问题','2个工作日内','纳入问题清单并给出处理计划','在下一维护版本修复，完成验证后关闭'),
('P4 建议','优化建议、文案、非缺陷需求或新增功能','3个工作日内确认是否属于质保范围','不承诺临时恢复时限','新增功能按需求变更流程评估，不纳入免费Bug修复')], [0.7, 2.25, 1.1, 1.85, 1.65])
for x in [
'支持渠道：工作日 9:00-18:00 使用项目群/工单/电话；P1 紧急问题使用双方确认的电话或项目群，并不构成未经合同约定的 7×24 服务。',
'处理闭环：客户提交现象、时间、账号、任务 ID、原始文件标识和日志摘要；服务商登记问题、确认等级、定位原因、提供临时措施、修复版本、回归结果和关闭记录。',
'质保范围：验收后 3 个月内包含系统 Bug 修复、部署问题协助和远程技术支持；不包含新增功能、客户自行修改配置导致的问题、硬件/操作系统故障和全量数据治理。']:
    bullet(x)

# Service
doc.add_heading('十、交付物与售后服务', level=1)
table(['交付物','形式'], [
('需求规格说明书、字段字典、规则确认表、验收用例','DOCX/PDF'),
('总体架构、数据模型、部署拓扑和安全方案','DOCX/PDF/架构图'),
('AI-BOM智能体程序包及配置文件','可部署程序包、Docker Compose/YAML、配置模板、镜像/安装脚本、版本清单和回滚说明；源代码按合同约定交付'),
('知识库初始数据、导入模板、导入/校验脚本','数据文件+脚本'),
('测试报告（功能、准确性、批量稳定性、部署检查）','DOCX/PDF'),
('部署配置手册、用户操作手册、知识库维护说明','DOCX/PDF'),
('培训记录、问题清单、验收确认单','DOCX/PDF')], [3.8, 3.8])
para('质保期建议沿用招标要求：验收后免费质保 3 个月，包含 Bug 修复、远程技术支持和部署问题协助；不包含新增功能、数据全量治理及客户环境硬件故障。工作日收到问题后 4 小时内响应，重大故障优先远程处理并持续跟踪；具体等级和响应时限以合同为准。')

# Assumptions checklist
doc.add_heading('十一、启动前需甲方确认的事项', level=1)
for x in [
'首期订单输入格式、每日/每批订单量、最大批量规模和结果导出模板。',
'历史 BOM 数量、字段样例、版本规则、物料编码现状及可提供的数据负责人。',
'首期覆盖的产品系列、色号范围、辅料范围和必须固化的业务规则。',
'服务器是否已有，是否具备 GPU，内网操作系统/容器环境和账号权限。',
'本地模型路线、模型许可、是否允许访问客户认可的内网模型服务。',
'客户业务验收人员、系统管理员、业务管理员及每周规则确认时间。']:
    bullet(x)

doc.add_heading('十二、相关案例响应说明', level=1)
para('招标文件要求提供“工业 BOM 解析生成、制造文档类 AI 智能体落地案例”。本方案不虚构项目经历。若投标方拥有可核验的同类案例，应在正式投标文件中补充案例名称、客户行业（经客户许可）、实施范围、上线时间、交付成果、可验证联系人或证明材料，并说明与本项目的相似点和差异。若暂无可核验同类案例，建议如实写明“暂无可核验的同类生产落地案例，可提供受限范围 POC/样例验证”，并将首期样本验证、人工确认和分阶段验收作为风险控制安排。')

# footer
for section in doc.sections:
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = footer.add_run('铅笔制造 AI-BOM 智能体整体实施方案 | 机密')
    run.font.size = Pt(8)
    run.font.color.rgb = RGBColor.from_string('999999')

# Core properties
doc.core_properties.title = '铅笔制造AI-BOM智能体整体实施方案'
doc.core_properties.subject = '智能体架构、私有化部署、BOM知识库及人天估算'
doc.core_properties.author = '项目实施团队'
doc.save(OUT)
print(OUT)
