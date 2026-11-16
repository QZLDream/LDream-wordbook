"""把一批英文句子机翻成中文，结果追加到缓存文件（key \t 英文 \t 中文），已翻过的跳过。
用法: python mt_sentences.py 输入.tsv 输出.tsv [ctranslate2模型目录]   （输入每行: key \t 英文）
模型: ct2-transformers-converter --model Helsinki-NLP/opus-mt-en-zh --output_dir en-zh-ct2"""
import sys, time, os, ctranslate2
from transformers import AutoTokenizer
src_file, cache = sys.argv[1], sys.argv[2]
done = set()
if os.path.exists(cache):
    done = {l.split("\t", 1)[0] for l in open(cache, encoding="utf-8")}
rows = [l.rstrip("\n").split("\t", 1) for l in open(src_file, encoding="utf-8")]
rows = [r for r in rows if len(r) == 2 and r[0] not in done]
tok = AutoTokenizer.from_pretrained("Helsinki-NLP/opus-mt-en-zh")
tr = ctranslate2.Translator(sys.argv[3] if len(sys.argv) > 3 else "en-zh-ct2", device="cpu", inter_threads=1, intra_threads=2)
t = time.time()
with open(cache, "a", encoding="utf-8") as f:
    for i in range(0, len(rows), 64):
        chunk = rows[i:i + 64]
        src = [tok.convert_ids_to_tokens(tok.encode(en)) for _, en in chunk]
        out = tr.translate_batch(src, beam_size=4, max_batch_size=64)
        for (k, en), o in zip(chunk, out):
            zh = tok.decode(tok.convert_tokens_to_ids(o.hypotheses[0]), skip_special_tokens=True).replace("\t", " ").replace("\n", " ")
            f.write(f"{k}\t{en}\t{zh}\n")
        f.flush()
        if i % 6400 == 0: print(i, len(rows), round(time.time() - t), flush=True)
print("done", len(rows), round(time.time() - t), flush=True)
