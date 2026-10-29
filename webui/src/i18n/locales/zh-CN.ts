/**
 * Panel copy, Chinese. This is the reference catalogue: every key here must also
 * exist in `en-US.ts`, and a test compares the two key sets so a half-translated
 * release fails the build instead of shipping blank labels.
 *
 * Only interface text lives here. Nothing from the bot's own replies — those are
 * translated on the server (see `src/soapbot/i18n`), because the language of a group
 * reply and the language of the console are chosen by different people.
 */
export default {
  'app.console': '控制台',
  'app.refresh': '刷新',
  'app.refreshing': '刷新中…',
  'app.health.online': 'API 在线',
  'app.health.unreachable': 'API 不可达',
  'app.health.connecting': '连接中',
  'app.auth.token': 'TOKEN',
  'app.auth.loopback': '本机直连',
  'app.auth.invalid': '令牌失效',
  'app.auth.none': '未认证',
  'app.footer.schema': 'schema',
  'app.footer.version': '版本',

  'nav.01': '总览',
  'nav.02': '运行状态',
  'nav.03': '插件',
  'nav.04': '安全审计',
  'nav.05': '记忆与知识库',
  'nav.06': '额度审批',
  'nav.07': '模型与人格',
  'nav.08': '运行日志',
  'nav.09': '流水线追踪',
  'nav.10': '运行指标',
  'nav.11': '插件包安装',
  'nav.12': '系统设置',

  'locale.label': '界面语言',
  'locale.zh': '中文',
  'locale.en': 'English',
  'locale.hint': '只影响这一台浏览器，不影响机器人在群里说话的语言',

  'settings.saved': '已保存',
  'settings.save': '保存',
  'settings.saving': '保存中…',
  'settings.pendingRestart': '待重启生效',

  'settings.language.title': '语言',
  'settings.language.reply': '回复语言',
  'settings.language.replyHint': '机器人发到群里的语言。人格卡里的 locale 字段可以按群覆盖它。写入 .env，重启后生效。',

  'settings.voice.title': '语音',
  'settings.voice.inbound': '把群里的语音消息转写成文本',
  'settings.voice.inboundHint': '每条语音会消耗一次 Provider 转写调用；失败时以 [语音] 占位，不会编造内容。',
  'settings.voice.outbound': '把回复合成为语音发出',
  'settings.voice.missingExtra': '未安装语音合成依赖，开关已置灰。安装后重启：',
  'settings.voice.voice': '音色',

  'settings.mcp.title': 'MCP 外部工具',
  'settings.mcp.name': '服务器',
  'settings.mcp.state': '状态',
  'settings.mcp.tools': '工具数',
  'settings.mcp.error': '错误',
  'settings.mcp.ok': '正常',
  'settings.mcp.failed': '失败',
  'settings.mcp.empty': '未配置 MCP 服务器。在 config/mcp.yaml 声明后重启。',

  'settings.runtime.title': '运行时信息',
  'settings.runtime.version': '版本',
  'settings.runtime.schema': '数据库 schema',
  'settings.runtime.expected': '本版本期望',
  'settings.runtime.dataDir': '数据目录',
  'settings.runtime.envFile': '配置文件',
  'settings.runtime.restartHint': '以上设置写入 .env，需要重启进程才会生效——面板不会假装它已经生效。',
  'settings.runtime.startupErrors': '启动时记录的告警：',
}
