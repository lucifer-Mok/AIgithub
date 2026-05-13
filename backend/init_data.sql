-- AI GitHub Tracker 初始化数据
-- 执行前请确保已创建 ai_github 数据库和所有表

-- 分类数据
INSERT IGNORE INTO ai_github.categories (name, slug, description, icon, sort_order) VALUES
('大语言模型', 'llm', 'LLM、GPT、Claude等大语言模型相关', '🧠', 1),
('RAG检索增强', 'rag', '检索增强生成、向量数据库、知识库', '🔍', 2),
('AI Agent', 'agent', 'AI智能体、自主代理、多Agent框架', '🤖', 3),
('MCP协议', 'mcp', 'Model Context Protocol相关工具和服务', '🔌', 4),
('图像视觉', 'vision', '图像生成、视觉理解、多模态', '🎨', 5),
('语音音频', 'audio', '语音识别、TTS、音频处理', '🎵', 6),
('模型训练', 'training', '模型训练、微调、RLHF', '⚙️', 7),
('模型推理', 'inference', '推理加速、部署、量化', '⚡', 8),
('AI工具链', 'toolchain', 'Prompt工程、开发框架、SDK', '🛠️', 9),
('数据集', 'dataset', '训练数据集、评测基准', '📊', 10),
('AI安全', 'safety', 'AI对齐、安全、红队测试', '🛡️', 11),
('具身智能', 'robotics', '机器人、具身AI、强化学习', '🦾', 12),
('代码生成', 'codegen', 'AI编程助手、代码生成、自动化', '💻', 13),
('其他AI', 'other', '其他AI相关项目', '✨', 14);

-- 自定义追踪规则（初始数据）
INSERT IGNORE INTO ai_github.custom_tracks (track_type, value, min_stars, source_repo, description, is_active) VALUES
-- 追踪指定 Repo
('repo', 'obra/superpowers', 0, 'obra/superpowers', 'agentic skills framework', 1),
('repo', 'nexu-io/open-design', 0, 'nexu-io/open-design', 'Claude Design 开源替代品', 1),
-- 关键词追踪
('keyword', 'agentic skills framework', 1000, 'obra/superpowers', '从 obra/superpowers 自动提取', 1),
('keyword', 'open source claude alternative', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('keyword', 'agent-skills', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('keyword', 'ai-agents', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('keyword', 'ai-design', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('keyword', 'byok', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('keyword', 'claude', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
-- Topic 追踪
('topic', 'agent-skills', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('topic', 'ai-agents', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('topic', 'ai-design', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('topic', 'byok', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1),
('topic', 'claude', 1000, 'nexu-io/open-design', '从 nexu-io/open-design 自动提取', 1);
