const labels: Record<string, string> = {
 company:'公司', role:'职位', name:'名称', title:'标题', text:'内容', bullets:'工作成果',
 description:'描述', start_date:'开始时间', end_date:'结束时间', technologies:'技术',
 school:'学校', degree:'学历', major:'专业', phone:'电话', email:'邮箱', location:'城市',
};
export function upstreamValue(value: unknown): string {
 if (value == null) return '（无）';
 if (value === '') return '（空）';
 if (Array.isArray(value)) return value.length ? value.map(v=>`• ${upstreamValue(v)}`).join('\n') : '（空列表）';
 if (typeof value === 'object') return Object.entries(value).map(([k,v])=>`${labels[k] ?? k}：${upstreamValue(v)}`).join('\n') || '（空）';
 return String(value);
}
