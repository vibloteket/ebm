from ebm import TileBase, TileBuilder

BLUE = (22, 114, 212, 255)
GREEN = (40, 200, 90, 255)
RED = (230, 65, 65, 255)
WALL = (49, 90, 168, 255)
CLEAR = (0, 0, 0, 0)

class ZigZag(TileBase):
    author = "Victor"

    def build(self, b: TileBuilder):

        # triangles right side
        b.static_segment((370,80), (398,70))
        b.static_segment((370,80), (398,90))

        b.static_segment((370,200), (398,190))
        b.static_segment((370,200), (398,210))

        # triangles left side
        b.static_segment((2,230), (30,240))
        b.static_segment((2,250), (30,240))

                
        # start leaning segments
        b.static_segment((100,30), (360,120))
        b.static_segment((2,150), (360,160))

        # left and right walls
        b.static_segment((2,170), (2,230))
        b.static_segment((2,250), (2,310))
        
        b.static_segment((398,40), (398,190))
        b.static_segment((398,210), (398,270))
        
        # zig-zag rails
        b.static_segment((30,160), (360,160))
        b.static_segment((40,200), (370,200))
        b.static_segment((30,240), (360,240))
        b.static_segment((40,280), (370,280))


        # small leaning parts, to the right
        b.static_segment((370,280), (398,270))
        
        # small leaning parts, to the left
        b.static_segment((2,170), (30,160))
        b.static_segment((2,310), (30,320))        

        
        # trapdoor floor
        b.static_segment((30,320), (180,320), surface_velocity=(200, 0))
        b.static_segment((220,320), (398,320))
        self.scanner = Scanner(b)

    def update(self, b, dt):
        self.scanner.update(dt)

class Scanner:
    GROW = 0.15
    SCAN = 0.20
    COLOR_TIME = 0.30
    PUSH = 400

    def __init__(self, b):
        self.phase = "ready"
        self.timer = 0.0
        self.ball = None
        self.go_right = True  # Första bollen höger, nästa nedåt.
        self.recolor = []

        self.floor = b.static_segment((180, 320), (220, 320), 2)
        # Fysiska väggar stänger direkt; uppväxandet är en kort animation.
        # Då kan nästa boll inte komma in medan animationen pågår.
        self.left = b.static_segment((180, 282), (180, 320), 2, fill_color=CLEAR)
        self.right = b.static_segment((220, 282), (220, 320), 2, fill_color=CLEAR)
        self.left.pause()
        self.right.pause()
        self.walls = [
            b.visual_segment((x, 320), (x, 320), 2, fill_color=CLEAR)
            for x in (180, 220)
        ]
        sensor = b.sensor_box(196, 282, 204, 318)
        b.on_ball_contact(sensor, pre_solve=self._capture)

    def _capture(self, event):
        if self.phase != "ready":
            return
        ball = event.ball
        x, y = ball.position
        if x < 200 or ball.velocity[0] < 0 or abs(y - (318 - ball.radius)) > 4:
            return
        if ball.radius > 18:
            raise ValueError("Skannerns öppning är för smal för den här bollen")
        self.ball = ball
        self.phase = "closing"
        self.timer = 0.0
        self.left.resume()
        self.right.resume()
        for wall in self.walls:
            wall.set_fill_color(WALL)
        self._hold()

    def _hold(self):
        # Håll kvar bollen under hela skanningen, inte bara ett fysiksteg.
        self.ball.set_position((200, 318 - self.ball.radius))
        self.ball.set_velocity((0, 0))

    def update(self, dt):
        pending = []
        for ball, remaining in self.recolor:
            remaining -= dt
            if remaining > 0:
                pending.append((ball, remaining))
            else:
                try:
                    ball.set_fill_color(BLUE)
                except PermissionError:
                    pass  # Handoff har redan återställt färgen.
        self.recolor = pending
        if self.phase == "ready":
            return

        self.timer += dt
        if self.phase == "closing":
            self._hold()
            height = 38 * min(1, self.timer / self.GROW)
            for x, wall in zip((180, 220), self.walls):
                wall.set_segment_points((x, 320), (x, 320 - height))
            if self.timer >= self.GROW:
                self.ball.set_fill_color(GREEN if self.go_right else RED)
                self.phase, self.timer = "scanning", 0.0

        elif self.phase == "scanning":
            self._hold()
            if self.timer >= self.SCAN:
                if self.go_right:
                    self.right.pause()
                    self.walls[1].set_fill_color(CLEAR)
                    self.ball.set_velocity((self.PUSH, 0))
                else:
                    self.floor.pause()
                self.recolor.append((self.ball, self.COLOR_TIME))
                self.phase = "releasing"

        elif self.phase == "releasing":
            try:
                x, y = self.ball.position
                r = self.ball.radius
                clear = x - r > 222 if self.go_right else y - r > 322
            except PermissionError:
                clear = True  # Bollen har redan lämnat tile:n.
            if clear:
                if not self.go_right:
                    self.floor.resume()
                    self.right.pause()
                self.left.pause()
                for x, wall in zip((180, 220), self.walls):
                    wall.set_fill_color(CLEAR)
                    wall.set_segment_points((x, 320), (x, 320))
                self.ball = None
                self.go_right = not self.go_right
                self.phase = "ready"
