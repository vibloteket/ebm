from ebm import TileBase, TileBuilder, Vec2d, Tween, ease
import random
import math

CLOUD_COLOR = (170,170,170,255)
GROUND_COLOR = (20,180,20,255)
TRUNK_COLOR = (89,51,29,255)
LEAF_COLOR = (58,95,7,255)
BUSH_COLOR = (74,125,27,255)

class Trees(TileBase):
    author = "Victor"
    enabled = False

    growing:list = []
    
    def build(self, b: TileBuilder):
                 
        # Clouds
        def c(x,y,r=30):
            b.visual_circle((x,y), r, fill_color=CLOUD_COLOR, stroke_color=None, foreground=True)
        # top left
        c(90,55)
        c(120,55)
        c(150,55)
        c(100,35)
        c(130,35)
        # top right
        #c(285,55,27)
        #c(325,55)
        #c(365,55)
        #c(320,35)
        #c(360,35)
        # bottom left
        c(35,145,28)
        c(70,145,30)
        c(105,145,28)
        c(60,130,28)
        c(90,130,28)
        # middle right
        c(210,100)
        c(250,100)
        c(295,100)
        c(230,80)
        c(280,75)
        
        # Ground
        def g(x1,y1,x2,y2):
            s = b.static_segment((x1,y1), (x2,y2), 6, fill_color = GROUND_COLOR, 
                             stroke_color = None, foreground=True)
            
        g(6,370, 160, 380)
        g(240,320, 394, 345)
        
        # Trunk 1
        pos1 = Vec2d(100,380)
        p = [
            pos1 + (-15,0),
            pos1 + (15,0),
            pos1 + (11, -100),
            pos1 + (-11, -100)
        ]
        b.visual_polygon(p, fill_color=TRUNK_COLOR, stroke_color=None)

        # Leaves 1
        def c(p,r=37):
            b.visual_circle(p, r, fill_color=LEAF_COLOR, stroke_color=None, foreground=False)
        c(pos1 + (-40,-120))
        c(pos1 + (-50,-130))
        c(pos1 + (-10,-150))
        c(pos1 + (15,-110))
        c(pos1 + (20,-150))
        c(pos1 + (60,-120))

        # Trunk 2
        pos2 = Vec2d(300,341)
        p = [
            pos2 + (-14,0),
            pos2 + (14,0),
            pos2 + (10, -120),
            pos2 + (-10, -120)
        ]
        b.visual_polygon(p, fill_color=TRUNK_COLOR, stroke_color=None)

        # Leaves 2
        def c(p,r=35):
            b.visual_circle(p, r, fill_color=LEAF_COLOR, stroke_color=None, foreground=False)
        c(pos2 + (-40,-140))
        c(pos2 + (-50,-150))
        c(pos2 + (-10,-180))
        c(pos2 + (15,-130))
        c(pos2 + (20,-190))
        c(pos2 + (60,-160))

        
        # Bush
        def c(x,y,r=20):
            b.static_circle((x,y), r, fill_color=BUSH_COLOR, stroke_color=None)
        c(259, 315, 20)
        c(284, 305, 20)
        c(274, 295, 20)
        c(274, 322, 20)
        c(244, 322, 20)
        c(254, 302, 20)

        # catching balls
        sensor1 = b.sensor_segment((40,160),(115, 121), 1)
        sensor2 = b.sensor_segment((80,70),(170, 70), 1)
        sensor3 = b.sensor_segment((185,110),(300, 110), 1)
        self.growing = []
        def catch_ball(event):
            ball = event.ball
            ball.pause()

            spawn_center = random.choice([
                (140,257),
                (325,216)
            ])
            p = random_in_circle(spawn_center, 50)
            #p = random.choice(growing_areas)
            
            circle = b.visual_circle(p, 1, dynamic=True, fill_color=(22, 114, 212, 255),
                                     stroke_color=(12, 63, 143, 255), foreground=True)
            anim = Tween(1, 15, duration=2, apply=circle.set_radius,
                    easing=ease.in_out_sine)
            d = {
                "ball": ball,
                "circle": circle,
                "anim": anim
            }
            self.growing.append(d)
        
            
        b.on_ball_contact(sensor1, begin=catch_ball)
        b.on_ball_contact(sensor2, begin=catch_ball)
        b.on_ball_contact(sensor3, begin=catch_ball)

    def update(self, b, dt):
        done = []
        for d in self.growing:
            d['anim'].update(dt)
            if d['anim'].done:
                done.append(d)
        for d in done:
            self.growing.remove(d)
            #print(d['circle'].center)
            d['ball'].set_position(d['circle'].center)
            d['ball'].set_velocity((0, 0))
            d['ball'].resume()
            
            b.remove(d['circle'])

def random_in_circle(center, radius, *, rng=None):
    rng = random if rng is None else rng
    angle = rng.uniform(0, 2 * math.pi)
    distance = radius * math.sqrt(rng.random())
    return Vec2d(*center) + Vec2d(
        math.cos(angle), math.sin(angle)
    ) * distance
