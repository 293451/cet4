# 页面模板说明

> `page.html` —— 每日精读页面的骨架。改版式只动这个文件，不用碰 Python。

## 怎么用

`render.py` 读这个文件，把 `@@XXX@@` 换成真实内容，写到 `dist/day-XX.html`。

**改模板 → 重跑 `python build/make.py --day 01 --no-tts` → 立刻看到效果。**

## 占位符清单

| 占位符 | 内容 | 示例 |
|---|---|---|
| `@@DAY@@` | 第几天（两位） | `01` |
| `@@DATE@@` | 日期（月/日） | `10/13` |
| `@@TITLE@@` | 英文标题 | `A Library on the Coast` |
| `@@TITLE_CN@@` | 中文标题 | `海边的一座图书馆` |
| `@@UNIT@@` | 单元 | `Unit 1` |
| `@@RANGE@@` | 词序范围 | `1-30` |
| `@@ARTICLE@@` | **正文**（逐句对照，已渲染好） | 见下 |
| `@@NWORDS@@` | 单词数 | `30` |
| `@@WORDLIST@@` | **词卡列表**（已渲染好） | 见下 |

⚠️ **占位符必须用 `@@XXX@@` 格式**。不要用 `{XXX}` —— CSS 的 `.w { }` 和
JS 的 `function(){ }` 会和 Python 的 `str.format()` 冲突，报看不懂的 `KeyError`。
渲染用的是 `.replace()`，不是 `.format()`。

## `@@ARTICLE@@` 的结构

`render.py` 的 `render_article()` 生成，每句一个 `.pair`：

```html
<div class="pair" data-s0="43" data-s1="3925">
  <p class="en">
    Twenty years ago, a small town on the
    <span class="w" data-s="2176" data-e="2219">the</span>
    <span class="w target" data-s="2261" data-e="2475">coast</span> …
  </p>
  <p class="zh">二十年前，海边的一座小镇就是一个安静的世界，自成一格。</p>
</div>
```

- `data-s0` / `data-s1` —— 这句的起止毫秒（句子级高亮用）
- `.w` —— 每个词，`data-s` / `data-e` 是它的起止毫秒
- `.w.target` —— 今日目标词（橙色常亮）
- `.w.on` —— 正在念的词（JS 动态加）
- `.pair.now` —— 正在念的句子（JS 动态加，整句黄底）

## `@@WORDLIST@@` 的结构

`render.py` 的 `render_wordlist()` 生成，每个词一张可展开的卡：

```html
<details class="card">
  <summary>
    <span class="idx">07</span>
    <span class="word">convert</span>
    <span class="ipa">/kən'v3:rt/</span>
    <span class="pos">v.</span>
    <span class="cn">转变，改变；转换</span>
  </summary>
  <div class="body">
    <div class="sent">   课文  今天文章里那句</div>
    <div class="mnem">   记    刘晓燕的记忆法 ★书里原文</div>
    <div class="root">   根    词根拆解</div>
    <div class="zt">     真题  真题例句 ★书里原文</div>
    <div class="colloc"> 搭    固定搭配</div>
    <div class="fam">    族    同族词</div>
  </div>
</details>
```

字段缺了就整块不渲染，所以不用管"有些词没有记忆法"这种事。

## 三档显示模式

靠 `<body>` 上的 class 切换，纯 CSS：

| body class | 效果 |
|---|---|
| （无） | 双语 —— 英文 + 中文 |
| `mode-en` | 只看英文（`.zh` 隐藏）|
| `mode-zh` | 只看中文（`.en` 隐藏）|

按钮在 `.modes`，点完存 `localStorage`，下次打开记住。

## 关键设计决定（改之前先读）

1. **逐句对照，不是整篇分块**
   曾经把英文和中文分成上下两大块 → 英文 14429 字符、中文 472 字符，
   读完英文要滚很久才看到译文，边听边看根本对不上。**别改回分块。**

2. **滚动跟随按句，不按词**
   逐词滚动会一直晃。句子够大，滚动不频繁，视线稳。

3. **句子间空隙不清除高亮**
   `find()` 找不到区间时返回上一个下标，不是 `-1`。否则高亮会在词与词之间闪断。

4. **点词跳那个词，点句子空白跳那句**
   两个 handler，靠 `ev.target.classList.contains('w')` 区分。

5. **深色模式用 `prefers-color-scheme`**
   所有颜色走 CSS 变量（`:root`），改配色只动变量。

## 配色变量

```css
--bg      背景        --card   卡片底
--line    分隔线      --ink    正文
--dim     次要文字    --accent 主题橙（目标词）
--hi      高亮底      --hi-ink 高亮文字
```

改配色只动 `:root` 里这 8 个值，深色模式那组也要一起改。

## 手机适配

- 视口 `width=device-width, initial-scale=1`，最大宽度 720px 居中
- 播放器 `position:sticky` 吸顶
- 触控目标 ≥ 44px
- 微信内置浏览器可直接打开（无外部依赖，单文件自包含）
