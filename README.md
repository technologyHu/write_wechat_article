# write_wechat_article

## 下载文章视频

文章视频由 Git LFS 管理。普通 `git clone` 默认只检出视频的指针文件。
安装并启用 Git LFS 后，在仓库根目录运行以下命令即可下载当前版本的全部文章视频。

```powershell
git lfs install
git lfs pull --exclude=
```

只需要某篇文章的视频时，可以按路径下载：

```powershell
git lfs pull --exclude= --include='openjiuwen/扩展性特性宣发软文/article/**/assets/videos/*.mp4'
```
