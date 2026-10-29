# 第三方声明

本项目采用 Apache License 2.0，全文见仓库根目录的 `LICENSE`，版权归 mirxiong。

界面主题预设来自 [tweakcn](https://github.com/jnsahaj/tweakcn)，同样采用 Apache License 2.0。

- 仓库：https://github.com/jnsahaj/tweakcn
- 固定提交：`a3b47b37cba97dd637de517aab52c45ec0f83456`
- 源文件：`utils/theme-presets.ts`、`LICENSE`
- 本地副本：`frontend/vendor/tweakcn/`
- 生成产物：`frontend/src/lib/theme-catalog.generated.ts`、`frontend/public/theme-init.js`
- 许可证全文：`frontend/public/licenses/APACHE-2.0.txt`

本项目对上游预设做了结构化提取，只保留主题 ID、名称和 light/dark 样式，并在浏览器启动时注入 CSS 变量。运行时不访问 tweakcn.com。
