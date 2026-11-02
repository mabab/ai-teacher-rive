#!/usr/bin/env python3
"""Image to 3D with TRELLIS on its public Hugging Face Space (free, queued, ZeroGPU quota).
Input: model/ref_1.png. Output: model/teacher_trellis.glb.
Args: [ref image] [mesh_simplify, 0.5 = drop half the triangles] [output name]
Run with the agent venv (has gradio_client): agent/.venv/bin/python gen/gen_model_trellis.py
"""
import shutil
import sys
from pathlib import Path

from gradio_client import Client, handle_file

ROOT = Path(__file__).resolve().parent.parent
src = ROOT / "model" / (sys.argv[1] if len(sys.argv) > 1 else "ref_1.png")
c = Client("trellis-community/TRELLIS", verbose=False)
params = [p["parameter_name"] for p in c.view_api(print_info=False, return_format="dict")["named_endpoints"]["/generate_and_extract_glb"]["parameters"]]
print("params", params)
c.predict(api_name="/start_session")
pre = c.predict(image=handle_file(str(src)), api_name="/preprocess_image")
print("preprocessed", pre)
args = dict(image=handle_file(pre), multiimages=[], seed=0, ss_guidance_strength=7.5, ss_sampling_steps=12,
            slat_guidance_strength=3.0, slat_sampling_steps=12, multiimage_algo="stochastic",
            mesh_simplify=float(sys.argv[2]) if len(sys.argv) > 2 else 0.5, texture_size=2048)
res = c.predict(**{k: v for k, v in args.items() if k in params}, api_name="/generate_and_extract_glb")
print(res)
glb = next(x for x in res[1:] if isinstance(x, str) and x.endswith(".glb"))
out = ROOT / "model" / (sys.argv[3] if len(sys.argv) > 3 else "teacher_trellis.glb")
shutil.copy(glb, out)
print("wrote", out, out.stat().st_size)
