"""Meaningful analytic geometry checks; run with Blender Python."""
import sys, math
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'blender'))
from terrain_analysis import triangle_metrics, classify
from mathutils import Vector, Matrix
for degrees in (0, 5, 10, 20, 25, 30, 35, 40, 45, 60, 89):
    a,b,c = Vector((0,0,0)), Vector((1,0,0)), Vector((0,1,math.tan(math.radians(degrees))))
    for rotation in (Matrix.Identity(3), Matrix.Rotation(.93,3,'X') @ Matrix.Rotation(.47,3,'Y')):
        up = rotation @ Vector((0,0,1))
        pa,pb,pc = [rotation @ v + Vector((123,54,-7)) for v in (a,b,c)]
        for order in ((pa,pb,pc),(pc,pb,pa)):
            slope, area, horizontal = triangle_metrics(*order,up)
            assert abs(slope-degrees)<.002, (degrees,slope)
            assert abs(horizontal-.5)<.0001
assert [classify(d) for d in (0,10,10.01,25,25.01,35,35.01,45,45.01,90)] == [0,0,1,1,2,2,3,3,4,4]
try:
    triangle_metrics(Vector((0,0,0)),Vector((0,0,0)),Vector((1,0,0)),Vector((0,0,1)))
    raise AssertionError('Degenerate triangle accepted')
except ValueError: pass
print('PASS: analytic ramps, rotations, reversed winding, class boundaries and degenerate rejection')
