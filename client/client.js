window.__ModuleLoader__.load({id: "dsh-mineru-win7", factory: function(require) {
var module = {exports: {}}; var exports = module.exports;
var React = require("react");
var CONTRACT = {
  "package": "dsh-mineru-win7",
  "face": "host",
  "schemas": [],
  "model": {
    "services": [],
    "events": [],
    "objects": []
  },
  "invocations": [
    {
      "id": "dsh-mineru-win7#mineruPanel.info",
      "service": "mineruPanel",
      "namespace": "mineruPanel",
      "method": "info",
      "invocation": {
        "kind": "direct"
      },
      "parameters": [],
      "result": {
        "mode": "strict",
        "typeSymbol": "dsh-mineru-win7#Text",
        "schema": {
          "type": "string"
        }
      }
    },
    {
      "id": "dsh-mineru-win7#mineruPanel.run",
      "service": "mineruPanel",
      "namespace": "mineruPanel",
      "method": "run",
      "invocation": {
        "kind": "direct"
      },
      "parameters": [
        {
          "name": "agent",
          "wire": "agentId",
          "source": "lookup",
          "lookup": "agent",
          "codec": {
            "mode": "strict",
            "typeSymbol": "@deepseek-ai/dsh-session/types#SessionId",
            "schema": {
              "type": "string"
            }
          }
        },
        {
          "name": "operation",
          "wire": "operation",
          "source": "json",
          "codec": {
            "mode": "strict",
            "typeSymbol": "dsh-mineru-win7#Text",
            "schema": {
              "type": "string"
            }
          }
        },
        {
          "name": "arguments",
          "wire": "arguments",
          "source": "json",
          "codec": {
            "mode": "strict",
            "typeSymbol": "dsh-mineru-win7#Text",
            "schema": {
              "type": "string"
            }
          }
        }
      ],
      "result": {
        "mode": "strict",
        "typeSymbol": "dsh-mineru-win7#Text",
        "schema": {
          "type": "string"
        }
      },
      "cancellation": {
        "parameter": "signal"
      }
    }
  ]
};
// Optional panel in the pinned original shell. Document content remains plain text.
exports.inject = ['slots', 'remote'];
exports.apply = async function apply(ctx) {
  const contribution = {package: CONTRACT.package, descriptors: JSON.parse(JSON.stringify(CONTRACT.invocations))};
  for (const row of contribution.descriptors) {
    for (const codec of [...row.parameters.map(item => item.codec), row.result]) {
      codec.schema = {parse(value) { if (typeof value !== 'string') throw new Error('Expected text'); return value; }};
    }
  }
  const unmount = await ctx.remote.$mount(contribution);
  ctx.effect(() => unmount);
  const remote = ctx.get('remote.mineruPanel');
  function decode(reply) {
    if (!reply.ok) throw new Error(reply.error?.message || 'MinerU 连接失败');
    return JSON.parse(reply.value);
  }
  const initial = decode(await remote.info());
  if (!initial.enabled) return;
  const h = React.createElement;
  const fieldStyle = {width: '100%', padding: 8, boxSizing: 'border-box', marginBottom: 10, border: '1px solid #b9c5c9', borderRadius: 6, color: '#152d36', background: '#fff'};
  const buttonStyle = {padding: '7px 11px', border: '1px solid #b9c5c9', borderRadius: 6, background: '#fff', color: '#152d36', cursor: 'pointer'};
  const messages = {HEALTH_RESPONSE: '已收到健康响应，请确认各服务组件就绪。', TASK_SUBMITTED: '任务已提交。', TASK_STATUS: '任务状态已更新。',
    RESULT_SAVED: '结果已保存，可分段阅读。', RESULT_CACHED: '已校验并读取本地缓存。', ARTIFACT_TEXT: '已读取本段内容。', TASKS: '任务列表已刷新。',
    RESULT_NOT_READY: '解析尚未完成，请稍后刷新。', BACKGROUND_WAIT_STARTED: '已开始后台等待，完成后由 DSH 通知。', LOCAL_TASK_FORGOTTEN: '本地任务已清理。'};

  function Panel() {
    const [open, setOpen] = React.useState(false);
    const [info, setInfo] = React.useState(initial);
    const [agent, setAgent] = React.useState(initial.agents[0]?.id || '');
    const [tasks, setTasks] = React.useState([]);
    const [selected, setSelected] = React.useState('');
    const [path, setPath] = React.useState('');
    const [busy, setBusy] = React.useState(false);
    const [notice, setNotice] = React.useState('选择会话后提交文件，或检查连接。');
    const [text, setText] = React.useState('');
    const [cursor, setCursor] = React.useState(0);
    const [eof, setEof] = React.useState(false);
    const [job, setJob] = React.useState(null);
    const alive = React.useRef(true);
    const generation = React.useRef(0);
    React.useEffect(() => () => { alive.current = false; generation.current++; }, []);
    React.useEffect(() => { generation.current++; setTasks([]); setSelected(''); setText(''); setCursor(0); setJob(null); }, [agent]);

    async function run(operation, args = {}) {
      if (!agent) throw new Error('请先在 DSH 创建一个会话，再选择该会话。');
      return decode(await remote.run(agent, operation, JSON.stringify(args)));
    }
    async function refresh() {
      const result = await run('list');
      if (!result.ok) throw new Error(result.message);
      return result.tasks;
    }
    async function action(operation, args = {}) {
      const current = generation.current;
      setBusy(true);
      try {
        const result = await run(operation, args);
        if (!alive.current || current !== generation.current) return;
        const stopped = operation === 'job_kill' && result.outcome;
        setNotice(stopped ? (result.outcome === 'already-finished' ? '后台等待已结束。' : '已请求停止本地等待，远端任务继续运行。') : messages[result.code] || result.message || result.code);
        if (result.task) setSelected(result.task.task_id);
        if (result.job_id) setJob({id: result.job_id, taskId: result.task.task_id});
        if (stopped) setJob(null);
        if (result.code === 'RESULT_SAVED' || result.code === 'RESULT_CACHED') {
          setJob(current => current?.taskId === result.task.task_id ? null : current);
        }
        if (operation === 'read' && result.ok) { setText(result.text); setCursor(result.next_offset); setEof(result.eof); }
        const updated = operation === 'list' ? result.tasks || [] : await refresh();
        if (alive.current && current === generation.current) {
          setTasks(updated);
          if (operation === 'forget') {setSelected(''); setText(''); setCursor(0);}
        }
      } catch (error) {
        if (alive.current && current === generation.current) setNotice(error.message);
      } finally { if (alive.current) setBusy(false); }
    }
    async function show() {
      setOpen(value => !value);
      try {
        const value = decode(await remote.info());
        if (!alive.current) return;
        setInfo(value);
        setAgent(current => value.agents.some(item => item.id === current) ? current : value.agents[0]?.id || '');
      } catch (error) { if (alive.current) setNotice(error.message); }
    }
    const task = tasks.find(item => item.task_id === selected);
    const controls = {display: 'flex', flexWrap: 'wrap', gap: 7, marginBottom: 12};
    function button(label, operation, args, disabled = false) {
      return h('button', {type: 'button', style: buttonStyle, disabled: busy || disabled, onClick: () => action(operation, args)}, label);
    }
    return h('div', {style: {position: 'fixed', right: 18, bottom: 18, zIndex: 999, pointerEvents: 'auto', font: '14px/1.5 system-ui, sans-serif', color: '#152d36'}},
      open ? h('section', {'aria-label': 'MinerU 文档解析', style: {width: 'min(460px, calc(100vw - 36px))', maxHeight: 'min(760px, calc(100vh - 90px))', overflowY: 'auto', padding: 18, boxSizing: 'border-box', border: '1px solid #c5d2d4', borderRadius: 12, background: '#f8fbfb', boxShadow: '0 10px 45px #173b4226', marginBottom: 10}},
        h('header', {style: {display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12}},
          h('strong', {style: {fontSize: 18}}, 'MinerU 文档解析'), h('button', {style: buttonStyle, onClick: () => setOpen(false), 'aria-label': '关闭 MinerU'}, '关闭')),
        h('details', {}, h('summary', {style: {cursor: 'pointer'}}, '连接设置'),
          h('p', {}, info.baseURL || '尚未配置服务地址'),
          h('p', {}, '连接配置由 DSH 的 MinerU 插件设置管理，修改后重启生效。'),
          h('small', {}, `${info.protocol} · ${info.officeMode} · ${info.credentialRef ? '使用凭据引用' : '未配置凭据'}`)),
        h('label', {}, '所属会话', h('select', {'aria-label': '所属会话', style: fieldStyle, value: agent, disabled: busy, onChange: event => setAgent(event.target.value)},
          h('option', {value: ''}, '选择会话'), info.agents.map(item => h('option', {key: item.id, value: item.id}, item.title || item.id)))),
        h('div', {style: controls}, button('检查连接', 'health'), button('刷新任务', 'list')),
        h('form', {onSubmit: event => {event.preventDefault(); action('submit', {file_path: path});}},
          h('label', {}, '文件路径', h('input', {'aria-label': '文件路径', placeholder: '输入此电脑上的 PDF、图片或 Office 文件路径', style: fieldStyle, value: path, onChange: event => setPath(event.target.value)})),
          h('button', {type: 'submit', style: {...buttonStyle, background: '#16665f', color: '#fff', marginBottom: 12}, disabled: busy || !path.trim() || !agent}, '提交解析')),
        h('label', {}, '解析任务', h('select', {'aria-label': '解析任务', style: fieldStyle, value: selected, disabled: busy, onChange: event => {setSelected(event.target.value); setText(''); setCursor(0); setEof(false);}},
          h('option', {value: ''}, tasks.length ? '选择任务' : '暂无任务，请提交或刷新'), tasks.map(item => h('option', {key: item.task_id, value: item.task_id}, `${item.source_name} · ${item.status}`)))),
        h('div', {style: controls}, button('刷新状态', 'status', {task_id: selected}, !selected), button('获取结果', 'result', {task_id: selected}, !selected),
          button('后台等待', 'wait', {task_id: selected, background: true}, !selected),
          job?.taskId === selected ? button('停止本地等待', 'job_kill', {job_id: job.id}) : null),
        task?.directory ? h('p', {style: {overflowWrap: 'anywhere'}}, '结果目录：', task.directory) : null,
        h('div', {role: 'status', 'aria-live': 'polite', style: {padding: 10, borderRadius: 6, background: '#e6f1ef', marginBottom: 10}}, busy ? '处理中…' : notice),
        h('div', {style: controls}, button('阅读 Markdown', 'read', {task_id: selected, offset: 0}, !selected), button('下一段', 'read', {task_id: selected, offset: cursor}, !selected || !text || eof)),
        text ? h('pre', {'aria-label': '解析文本', style: {whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 260, overflowY: 'auto', background: '#fff', padding: 12, border: '1px solid #d7e1e2'}}, text) : null,
        h('p', {style: {fontSize: 12, color: '#52676e'}}, '停止等待仅停止本地轮询。忘记任务只清理本地记录与未修改的产物。'),
        h('button', {style: buttonStyle, disabled: busy || !selected, onClick: () => {if (window.confirm('清理此任务的本地记录和未修改产物？远端任务会保留。')) action('forget', {task_id: selected});}}, '忘记本地任务')
      ) : null,
      h('button', {style: {...buttonStyle, float: 'right', background: '#16665f', color: '#fff'}, 'aria-expanded': open, onClick: show}, 'MinerU'));
  }
  ctx.slots.inject('shell.overlay', () => ctx.slots.register({name: 'shell.overlay', id: 'mineru-win7'}, Panel));
};

return module.exports;
}});
//# sourceMappingURL=client.js.map
