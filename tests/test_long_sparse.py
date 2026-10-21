import unittest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor,QFont,QImage,QPainter,QLinearGradient
from PySide6.QtWidgets import QApplication
from document_assistant.long_stitch import VerticalStitcher
from tests.test_long_capture import make_page


class SparseChatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])
        make_page(200,100)  # Ensure offscreen Qt renders real glyphs.

    def page(self,repeated=False):
        page=QImage(760,1600,QImage.Format.Format_RGB32);page.fill(QColor('white'))
        p=QPainter(page);p.setFont(QFont('Segoe UI',13));p.setPen(QColor('#17324d'))
        for y in ([400,620,840] if repeated else [620]):
            p.setBrush(QColor('#e9f3ff'));p.setPen(QColor('#e9f3ff'));p.drawRoundedRect(560,y-28,175,48,14,14)
            p.setPen(QColor('#17324d'));p.drawText(578,y,'Unique item 42')
        p.end();return page

    def frame(self,page,offset,fade=True):
        frame=page.copy(0,offset,760,600)
        if fade:
            p=QPainter(frame);gradient=QLinearGradient(0,540,0,595)
            gradient.setColorAt(0,QColor(255,255,255,0));gradient.setColorAt(1,QColor(255,255,255))
            p.fillRect(0,540,760,60,gradient)
            p.setPen(QColor('#dddddd'));p.drawEllipse(QRectF(365,570,30,30));p.end()
        return frame

    def test_single_short_message_surrounded_by_blank_can_scroll_up(self):
        page=self.page();first=self.frame(page,200);current=self.frame(page,103)
        stitcher=VerticalStitcher(first);result=stitcher.append(current)
        self.assertEqual((result.status,result.added),('prepended',97))
        self.assertEqual(stitcher.image().copy(0,97,760,600),first)

    def test_single_message_downward_and_one_pixel_moves_are_preserved(self):
        page=self.page();stitcher=VerticalStitcher(self.frame(page,200,False))
        for offset in range(201,209):self.assertEqual(stitcher.append(self.frame(page,offset,False)).added,1)
        self.assertEqual(stitcher.append(self.frame(page,260,False)).added,52)
        self.assertEqual(stitcher.image(),page.copy(0,200,760,660))

    def test_sparse_pause_does_not_duplicate_content(self):
        page=self.page();first=self.frame(page,200);stitcher=VerticalStitcher(first)
        for _ in range(10):self.assertEqual(stitcher.append(first).status,'unchanged')
        self.assertEqual(stitcher.append(self.frame(page,103)).added,97)

    def test_sparse_high_dpi_rows_and_footer_scale_with_viewport(self):
        page=self.page()
        for ratio in (1,1.5,2):
            with self.subTest(ratio=ratio):
                width,height=round(760*ratio),round(600*ratio)
                # Native screen grabs crop one rasterized page; resizing two
                # independent viewport crops creates a false sampling phase.
                native=page.scaled(width,round(page.height()*ratio))
                def viewport(offset):
                    frame=native.copy(0,round(offset*ratio),width,height)
                    p=QPainter(frame);fade=QLinearGradient(0,540*ratio,0,595*ratio)
                    fade.setColorAt(0,QColor(255,255,255,0));fade.setColorAt(1,QColor(255,255,255))
                    p.fillRect(QRectF(0,540*ratio,width,60*ratio),fade);p.end();return frame
                first=viewport(200);current=viewport(103)
                result=VerticalStitcher(first).append(current)
                self.assertIn(result.added,(int(97*ratio),round(97*ratio)))

    def test_blank_without_an_anchor_is_rejected(self):
        blank=QImage(760,600,QImage.Format.Format_RGB32);blank.fill(QColor('white'))
        changed=blank.copy();p=QPainter(changed);p.fillRect(0,550,760,50,QColor('#fafafa'));p.end()
        self.assertEqual(VerticalStitcher(blank).append(changed).status,'no_overlap')

    def test_single_message_cannot_hide_changed_background_or_new_body(self):
        page=self.page();first=self.frame(page,200,False)
        current=self.frame(page,103,False);p=QPainter(current);p.fillRect(0,0,760,300,QColor('#eeeeee'));p.end()
        self.assertEqual(VerticalStitcher(first).append(current).status,'no_overlap')
        other=make_page(760,1600,seed=172);current=self.frame(other,103,False)
        p=QPainter(current);p.drawImage(500,450,self.frame(page,103,False).copy(500,450,260,100));p.end()
        self.assertEqual(VerticalStitcher(first).append(current).status,'no_overlap')

    def test_repeated_short_messages_do_not_pick_an_arbitrary_offset(self):
        page=self.page(repeated=True);first=self.frame(page,200,False)
        self.assertEqual(VerticalStitcher(first).append(self.frame(page,220,False)).status,'no_overlap')

    def test_continuous_sparse_chat_with_pause_and_direction_changes(self):
        page=QImage(760,3600,QImage.Format.Format_RGB32);page.fill(QColor('white'))
        p=QPainter(page);p.setFont(QFont('Segoe UI',13))
        for index,y in enumerate(range(160,3400,270)):
            p.setPen(QColor('#18364a'));p.drawText(80,y,f'Message {index:03}: unique topic {index*173+19}')
        p.end();stitcher=VerticalStitcher(self.frame(page,1100))
        offsets=list(range(1050,0,-50))+[50]*8+list(range(100,1650,50))+list(range(1550,1000,-50))
        low=high=1100
        for offset in offsets:
            low=min(low,offset);high=max(high,offset)
            result=stitcher.append(self.frame(page,offset))
            self.assertNotEqual(result.status,'no_overlap',f'continuous viewport at {offset}')
            self.assertEqual(stitcher.position,offset-1100)
            self.assertEqual(stitcher.height,600+high-low)


if __name__=='__main__':unittest.main()
