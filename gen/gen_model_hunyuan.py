#!/usr/bin/env python3
"""Image to textured 3D with Hunyuan3D-2 on its public Hugging Face Space.
Input: model/ref_1.png. Output: model/teacher_hunyuan.glb (+ _white.glb, the untextured shape).
Run with the agent venv: agent/.venv/bin/python gen/gen_model_hunyuan.py
"""
import shutil
import sys
from pathlib import Path

from gradio_client import Client, handle_file

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "model" / (sys.argv[1] if len(sys.argv) > 1 else "ref_1.png")
c = Client("tencent/Hunyuan3D-2", verbose=False)
res = c.predict(caption=None, image=handle_file(str(src)), mv_image_front=None, mv_image_back=None, mv_image_left=None,
                mv_image_right=None, steps=30, guidance_scale=5.0, seed=1234, octree_resolution=380,
                check_box_rembg=True, num_chunks=8000, randomize_seed=False, api_name="/shape_generation")
print(res[3] if len(res) > 3 else res)
for i, name in ((0, sys.argv[2] if len(sys.argv) > 2 else "teacher_hunyuan_white.glb"),):
    f = res[i]["value"] if isinstance(res[i], dict) else res[i]
    shutil.copy(f, ROOT / "model" / name)
    print("wrote", name, (ROOT / "model" / name).stat().st_size)
