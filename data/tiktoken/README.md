# Bundled tokenizer

This folder holds OpenAI's public `o200k_base` encoding, so token counting works
with no internet connection.

tiktoken looks up cached files by the sha1 of their download URL, so the file is
named `fb374d419588a4632f3f557e76b4b70aebbca790`
(= sha1 of `https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken`).
Its sha256 must be `446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d`.
`tokens.py` points `TIKTOKEN_CACHE_DIR` here before loading.

Source and license: this is OpenAI's public encoding file, published for use with
the [tiktoken](https://github.com/openai/tiktoken) package (MIT License), bundled
unmodified. The sha256 above proves it hasn't been altered.
