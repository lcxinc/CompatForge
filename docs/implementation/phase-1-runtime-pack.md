# Runtime Pack 内容存储纵向切片

Core `0.7.0` 建立本地 Runtime Pack 从 bundle 到 active digest 的首个闭环。

## 数据流

1. 读取 bundle 内的 Schema v1 manifest，并执行 DTO、标识符、portable path、唯一性和 digest 格式校验。
2. 生成排除 `digest`/`signature` 的规范化 manifest bytes，校验 pack SHA-256，并按 channel 执行 fail-closed 签名策略。
3. 流式复制每个 opaque artifact，在临时文件上计算 SHA-256；全部匹配后原子发布到内容寻址对象路径。
4. 发布规范化 manifest；最后原子更新 pack 的 active ref，此前的任何失败都不会改变可见版本。
5. `verify` 重新计算 manifest 与所有对象；`rollback` 仅在旧目标全部通过校验后切换 active ref。

## 本地布局

```text
runtime-packs/
  objects/sha256/<component-digest>
  manifests/sha256/<pack-digest>.json
  refs/<pack-id>/current.json
```

`current.json` 是唯一的激活点，并保存最多 32 个历史 digest。内容对象不包含 pack id，因此不同 Pack 可安全复用相同 artifact。

## CLI 验收

```bash
compatforge-cli runtime manifest-digest <manifest.json>
compatforge-cli runtime install <store-root> <bundle-root> <manifest-relative-path>
compatforge-cli runtime verify <store-root> <pack-digest>
compatforge-cli runtime rollback <store-root> <pack-id>
```

默认 CLI 使用拒绝所有签名的 verifier：未签名 preview/development 可用于本地开发；stable/candidate 和任何带 signature 的 manifest 在可信密钥 provider 接入前均拒绝。

## 非目标

- 网络下载、channel refresh 或 catalog；
- tar/zip/zstd 解包与 entrypoint 物化；
- Ed25519/P-256 密钥存储、撤销和透明日志；
- Wine/Translator/Graphics 专项 probe；
- 跨进程写锁和不可达对象垃圾回收。
