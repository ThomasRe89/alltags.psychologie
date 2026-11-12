import numpy as np
from PIL import Image, ImageFilter
from scipy.ndimage import gaussian_filter
def blot(seed, size, ink, paper, S=1080):
    rng=np.random.default_rng(seed)
    yy,xx=np.mgrid[0:S,0:S].astype(float)
    g=lambda x,y,s: np.exp(-(((xx-x)**2+(yy-y)**2)/(2*s*s)))
    f=np.zeros((S,S)); c=S/2
    for y in np.linspace(S*0.30,S*0.72,5): f+=g(c-rng.uniform(0,25),y,rng.uniform(35,60))
    for i in range(7): f+=g(rng.uniform(S*0.24,S*0.44),rng.uniform(S*0.26,S*0.74),rng.uniform(30,75))*rng.uniform(0.8,1.3)
    for i in range(9): f+=g(rng.uniform(S*0.16,S*0.36),rng.uniform(S*0.2,S*0.8),rng.uniform(6,14))*1.2
    for i in range(3): f-=g(rng.uniform(S*0.36,S*0.46),rng.uniform(S*0.35,S*0.65),rng.uniform(14,28))*1.4
    f=f+0.12*gaussian_filter(rng.normal(size=(S,S)),5)*9
    left=f[:, :S//2]; full=np.concatenate([left,left[:, ::-1]],axis=1)
    m=Image.fromarray(((full>0.55)*255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2.5))
    m=m.point(lambda v:255 if v>127 else 0).filter(ImageFilter.GaussianBlur(1.2))
    img=Image.new("RGB",(S,S),paper); img.paste(Image.new("RGB",(S,S),ink),(0,0),m)
    return img.resize((size,size), Image.LANCZOS)
