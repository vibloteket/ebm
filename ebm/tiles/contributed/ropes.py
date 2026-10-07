from ebm import TileBase, TileBuilder

class Ropes(TileBase):
    author = "Victor"
    enabled = False

    def build(self, b: TileBuilder):        
        # Add physical and visual components with b.
        # Coordinates are local to this 400 × 400 tile.
        c = (255,0,0,255)
        def make_rope(b: TileBuilder, x: float, y: float, length: float = 100) -> None:
            segment_length = 25
            half = segment_length / 2
            links = []
            for i in range(0, length, segment_length):
                body = b.dynamic_body((x, y + i + half))        
                b.segment_shape(body, (0, -half), (0, half), 2,
                                density=0.004, fill_color=c, stroke_color=None)
                links.append(body)
            b.pivot(links[0], (x, y))                           
            for i in range(len(links) - 1):
                b.pivot(links[i], links[i+1], (x, y + (i+1)*segment_length))             
            body = b.dynamic_body(links[-1].position)
            circle = b.circle_shape(body, (0,0), 6, stroke_color=c, fill_color=c, foreground=True)
            b.pivot(links[-1], body, (links[-1].position))
            #b.on_ball_contact(circle, )
            
        make_rope(b, 200,100)

        # funnel
        funnel_y = 250
        b.static_segment((2, funnel_y-30),(180,funnel_y))
        b.static_segment((220,funnel_y),(398, funnel_y-30))
        b.static_segment((180,funnel_y),(180,funnel_y+20))
        b.static_segment((220,funnel_y),(220,funnel_y+20))
        
        b.static_segment((200,330),(398,340))

