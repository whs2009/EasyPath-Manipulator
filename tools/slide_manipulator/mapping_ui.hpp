#include <FL/Fl.H>
#include <FL/Fl_Double_Window.H>
#include <FL/Fl_Hold_Browser.H>
#include <FL/Fl_Button.H>
#include <FL/Fl_Check_Button.H>
#include <FL/Fl_Spinner.H>
#include <FL/Fl_Choice.H>
#include <FL/Fl_Box.H>
#include <FL/Fl_Input.H>
#include <FL/Fl_Scroll.H>
#include <FL/Fl_Value_Slider.H>
#include <FL/Fl_Native_File_Chooser.H>
#include <FL/Fl_Menu_Item.H>
#include <FL/fl_draw.H>
#include <FL/fl_ask.H>
#include <string>
#include <vector>
#include <sstream>
#include <algorithm>
#include <cmath>
#ifdef _WIN32
#define API __declspec(dllexport)
#else
#define API __attribute__((visibility("default")))
#endif
using Call=int(*)(const char*,const char*,double,double,char*,int);
using Paint=int(*)(int,int,int,unsigned char*);
using std::string;
static Fl_Color teal(){return fl_rgb_color(22,116,95);}
static Fl_Color blue(){return fl_rgb_color(37,100,164);}
static Fl_Color muted(){return fl_rgb_color(83,102,95);}
static std::vector<string> lines(const string&s){std::istringstream in(s);std::vector<string> v;string line;
    while(std::getline(in,line))v.push_back(line);return v;}
struct Bridge {
    Call cmd; Paint paint;string result,error;
    bool send(const char*c,const string&s="",double a=0,double b=0){
        std::vector<char> buf(262144);int rc=cmd(c,s.c_str(),a,b,buf.data(),int(buf.size()));
        result=buf.data();if(rc)error=result;return rc==0;}
    string get(const char*c){return send(c)?result:"";}
};
static Fl_Box* caption(int x,int y,int w,const char*s,bool prominent=false){
    auto *p=new Fl_Box(x,y,w,23,s);p->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE|FL_ALIGN_CLIP);p->labelfont(FL_HELVETICA_BOLD);
    p->labelsize(prominent?19:14);p->labelcolor(prominent?teal():muted());return p;}
static void style(Fl_Button*b,Fl_Color bg){b->color(bg);b->labelcolor(FL_WHITE);b->labelfont(FL_HELVETICA_BOLD);}
static Fl_Hold_Browser* listbox(int x,int y,int w,int h){auto* b=new Fl_Hold_Browser(x,y,w,h);b->format_char(0);
    b->color(FL_WHITE);b->selection_color(teal());b->textsize(14);b->has_scrollbar(Fl_Browser_::BOTH);return b;}
static void fill(Fl_Hold_Browser*b,const std::vector<string>&v,int idx){int top=b->topline();b->clear();for(auto&s:v)b->add(s.c_str());
    if(idx>=0 && idx<(int)v.size())b->value(idx+1);if(top>0)b->topline(top);}
static void enable(Fl_Widget*w,bool on){if(on)w->activate();else w->deactivate();}
static bool choose(const char* title,Fl_Native_File_Chooser::Type type,const char* filter,std::vector<string>& out,const char* preset=nullptr){
    Fl_Native_File_Chooser dialog;dialog.title(title);dialog.type(type);dialog.filter(filter);if(preset)dialog.preset_file(preset);
    if(dialog.show()!=0)return false;for(int i=0;i<dialog.count();++i)out.emplace_back(dialog.filename(i));return !out.empty();}
struct Popup;
class Canvas:public Fl_Widget {
public:
    Bridge &b;int kind;Popup *pop=nullptr;int mx=0,my=0;
    Canvas(int x,int y,int w,int h,Bridge& bridge,int mode):Fl_Widget(x,y,w,h),b(bridge),kind(mode){}
    void draw() override{fl_push_clip(x(),y(),w(),h());if(w()>0 && h()>0 && (long long)w()*h()<=8388608){
        std::vector<unsigned char> rgb(size_t(w())*h()*3);if(!b.paint(kind,w(),h(),rgb.data()))fl_draw_image(rgb.data(),x(),y(),w(),h(),3);
        else{fl_color(FL_DARK3);fl_rectf(x(),y(),w(),h());fl_color(FL_WHITE);fl_draw("Preview unavailable",x()+16,y()+24);}}
        fl_pop_clip();}
    int handle(int) override;
};
struct Popup {
    Bridge &b;int kind;Fl_Double_Window win;Canvas* stage;Fl_Box *msg;Fl_Value_Slider *base=nullptr,*active=nullptr;
    Fl_Double_Window *actions=nullptr;Fl_Button *first=nullptr,*second=nullptr;bool is_delete=false,confirm=false;
    Fl_Choice* plane=nullptr;
    Popup(Bridge& bridge,int mode,const string& title,bool overlay,double bo,double ao,bool output=false):b(bridge),kind(mode),win(960,655){
        win.copy_label(title.c_str());win.begin();stage=new Canvas(0,0,960,600,b,kind);stage->pop=this;
        if(overlay){
            base=slider(117,"Base opacity",bo);active=slider(454,"Active frame opacity",ao);
        }
        if(output){
            plane=new Fl_Choice(66,613,242,27,"Frame");auto names=lines(b.get("titles"));
            for(size_t i=0;i<names.size();++i){plane->add("frame");plane->replace(int(i),names[i].c_str());}
            plane->value(std::stoi(b.get("display_index")));
            plane->callback([](Fl_Widget*,void*p){auto&u=*static_cast<Popup*>(p);u.call("out_frame","",u.plane->value());},this);
        }
        auto* fit=new Fl_Button(805,613,66,27,"Auto fit");fit->callback([](Fl_Widget*,void* p){static_cast<Popup*>(p)->call("autofit");},this);
        auto* done=new Fl_Button(877,613,67,27,"Done");done->callback(close_cb,this);
        msg=new Fl_Box(overlay?619:output?322:12,610,overlay?178:output?470:782,33);msg->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE|FL_ALIGN_CLIP);
        win.end();win.resizable(stage);win.size_range(900,530,2200,1540);win.set_modal();win.callback(close_cb,this);
    }
    static void close_cb(Fl_Widget*,void*p){auto&u=*static_cast<Popup*>(p);
        if(u.kind==1 && u.b.get("draft")=="1" && fl_choice("Discard this unsaved crop outline?","Keep drawing","Discard",nullptr)!=1)return;
        u.win.hide();}
    Fl_Value_Slider* slider(int x,const char*n,double v){auto*s=new Fl_Value_Slider(x,614,158,26,n);s->type(FL_HOR_NICE_SLIDER);
        s->align(FL_ALIGN_LEFT);s->bounds(0,1);s->step(.1);s->precision(1);s->value(v/10);s->selection_color(teal());
        s->callback([](Fl_Widget*,void*p){auto&u=*static_cast<Popup*>(p);u.call("opacity","",std::lround(u.base->value()*10),std::lround(u.active->value()*10));},this);return s;}
    bool call(const char*c,const string&s="",double x=0,double y=0){bool ok=b.send(c,s,x,y);if(!ok)msg->copy_label(b.error.c_str());stage->redraw();return ok;}
    void say(const char*s){msg->copy_label(s);}
    int key(int k,bool shift){
        if(shift&&plane&&(k==FL_Page_Up||k==FL_Page_Down)){
            if(call("display_plane","",k==FL_Page_Up?1:-1))plane->value(std::stoi(b.get("display_index")));return 1;}
        if(!shift || kind!=1)return 0;
        const char*c=k=='z'?"begin":k=='s'?"finish":k=='r'?"clear_draft":k=='a'?"back":k=='d'?"cut":nullptr;
        if(!c)return 0;
        if(call(c))say(k=='z'?"Recording crop":k=='s'?"Region saved":k=='d'?"Crop subtracted":k=='a'?"Drawing paused":"Draft cleared");return 1;}
    bool flip(int choice){return choice==0?call("flip"):choice==1?call("flop"):false;}
    ~Popup(){if(actions){actions->hide();delete actions;}}
    void dismiss(){actions->hide();stage->take_focus();}
    void apply(int n){
        if(!is_delete){flip(n);dismiss();return;}
        if(n==1){dismiss();return;}
        if(!confirm){confirm=true;actions->copy_label("Remove region and its placements?");
            first->copy_label("Confirm delete");first->take_focus();return;}
        if(call("region_delete"))say("Region and its placements removed.");dismiss();
    }
    void menu(bool region){
        if(!actions){
            actions=new Fl_Double_Window(242,94);first=new Fl_Button(10,9,222,32);second=new Fl_Button(10,51,222,32);
            first->callback([](Fl_Widget*,void*p){static_cast<Popup*>(p)->apply(0);},this);
            second->callback([](Fl_Widget*,void*p){static_cast<Popup*>(p)->apply(1);},this);
            actions->end();actions->set_modal();actions->callback([](Fl_Widget*,void*p){static_cast<Popup*>(p)->dismiss();},this);
        }
        is_delete=region;confirm=false;actions->copy_label(region?"Mapping region":"Placement");
        first->copy_label(region?"Delete mapping region...":"Flip horizontally");second->copy_label(region?"Cancel":"Flip vertically");
        int sx,sy,sw,sh;Fl::screen_work_area(sx,sy,sw,sh,Fl::event_x_root(),Fl::event_y_root());
        actions->position(std::clamp(Fl::event_x_root(),sx,std::max(sx,sx+sw-242)),
                          std::clamp(Fl::event_y_root(),sy+30,std::max(sy+30,sy+sh-94)));
        actions->show();first->take_focus();}
};
int Canvas::handle(int e){
    if(!pop)return 0; // Inline previews never edit, select, pan or intercept scrolling.
    // X11 may deliver input before the expose event, including immediately after a resize.
    if((e==FL_PUSH||e==FL_MOVE||e==FL_ENTER||e==FL_DRAG||e==FL_MOUSEWHEEL||e==FL_KEYDOWN||e==FL_SHORTCUT)
        && !b.send("viewport","",w(),h()))return 0;
    int px=Fl::event_x()-x(),py=Fl::event_y()-y();
    switch(e){
    case FL_FOCUS:case FL_UNFOCUS:return 1;
    case FL_MOVE:case FL_ENTER:
        mx=px;my=py;if(kind==1){b.send("point","",px,py);if(b.get("recording")=="1")redraw();}return 1;
    case FL_PUSH:{
        take_focus();mx=px;my=py;bool right=Fl::event_button()==FL_RIGHT_MOUSE;
        if(right && kind==1){if(pop->call("region_hit","",px,py)&&!b.result.empty())pop->menu(true);return 1;}
        if(!right && Fl::event_button()!=FL_LEFT_MOUSE)return 0;
        bool ok=pop->call("start",right?"right":"left",px,py);
        if(kind==2&&!right&&Fl::event_clicks()&&ok&&b.result!="-1"){pop->call("end");pop->menu(false);Fl::event_clicks(0);}return 1;}
    case FL_DRAG:mx=px;my=py;
        if(kind==1&&b.get("recording")=="1")pop->call("point","",px,py);else pop->call("motion","",px,py);return 1;
    case FL_RELEASE:pop->call("end");return 1;
    case FL_MOUSEWHEEL:pop->call("zoom",std::to_string(-Fl::event_dy()),px,py);return 1;
    case FL_KEYDOWN:case FL_SHORTCUT:
        if(!(Fl::event_state()&(FL_CTRL|FL_ALT|FL_META)))return pop->key(Fl::event_key(),Fl::event_state(FL_SHIFT)!=0);
    }
    return Fl_Widget::handle(e);
}
struct UI {
    Bridge b;
    Fl_Double_Window win{1130,680,"EasyPath | Slide Manipulator"};
    Fl_Scroll *strip;Fl_Button *tabs[23]{},*left,*right,*del,*add,*open,*whole,*region,*remove,*manip;
    Fl_Group *input,*layer,*output,*rule,*body;Canvas *preview,*outprev;
    Fl_Hold_Browser *inputs,*sources,*objects,*mergedSource;Fl_Input *name,*dist;
    Fl_Check_Button *srgb;Fl_Spinner *bits,*loss,*jxl;Fl_Choice *format;Fl_Box*status;
    Fl_Button *cancel,*outopen,*outwhole,*outregion,*outremove,*outalign,*generate,*facts,*reset;
    Fl_Hold_Browser *outobjects;std::vector<string> titles;int tab=0,fi=0,oi=-1,row=-1;bool exporting=false;
    static constexpr int OUT=21,RULE=22;
    UI(Call c,Paint p):b{c,p}{
        caption(20,11,415,"Manipulate mapping",true);
        strip=new Fl_Scroll(15,43,1100,54);strip->type(Fl_Scroll::HORIZONTAL);strip->begin();
        for(int i=0;i<23;++i){tabs[i]=new Fl_Button(16,46,60,31);tabs[i]->callback([](Fl_Widget*w,void*ptr){auto&u=*static_cast<UI*>(ptr);
            for(int i=0;i<23;++i)if(u.tabs[i]==w){u.select(i);return;}},this);}
        strip->end();
        body=new Fl_Group(16,104,1098,495);
        input=new Fl_Group(16,104,1098,495);
        caption(29,127,265,"Manipulation mapping work");btn(29,166,128,"Load project...","load");btn(165,166,137,"Save project as...","save");
        srgb=new Fl_Check_Button(29,222,335,28,"Assume sRGB if no profile");srgb->value(b.get("srgb_value")=="1");bind(srgb,"srgb");
        caption(337,127,330,"Selected slides");inputs=listbox(337,165,750,341);
        style(btn(337,520,144,"Open slides...","input"),teal());input->resizable(inputs);input->end();
        layer=new Fl_Group(16,104,1098,495);
        caption(26,114,240,"Frame name");name=new Fl_Input(26,144,334,29);name->maximum_size(120);name->when(FL_WHEN_CHANGED);bind(name,"name");
        caption(386,114,200,"Frame distance (mm)");dist=new Fl_Input(386,144,144,29);dist->tooltip("NA when not specified");dist->when(FL_WHEN_ENTER_KEY|FL_WHEN_RELEASE);bind(dist,"distance");
        caption(26,202,310,"Selected slides");caption(386,202,284,"Placed objects");caption(697,202,330,"Mapping preview");
        sources=listbox(26,236,345,218);bind(sources,"source");objects=listbox(386,236,294,218);bind(objects,"object");
        preview=new Canvas(697,236,392,218,b,0);
        open=btn(26,466,51,"Open","open");whole=btn(83,466,118,"Add whole slide","whole");region=btn(207,466,164,"Add segmented region","region");
        whole->labelsize(12);region->labelsize(12);
        open->tooltip("Open selected slide or Z plane to draw mapping regions");style(whole,blue());style(region,teal());
        remove=btn(386,466,130,"Remove placement","remove");
        manip=btn(697,466,149,"Open manipulation","align");style(manip,teal());
        add=btn(852,466,105,"Add frame","addframe");style(add,blue());del=btn(963,466,126,"Delete frame","deleteframe");style(del,fl_rgb_color(166,54,65));
        left=btn(697,506,114,"Switch left","left");right=btn(817,506,117,"Switch right","right");style(left,fl_rgb_color(151,91,22));style(right,fl_rgb_color(151,91,22));
        layer->resizable(preview);layer->end();
        output=new Fl_Group(16,104,1098,495);
        caption(26,124,327,"Selected slides");caption(378,124,290,"Placed objects");caption(690,124,396,"Mapping preview");
        mergedSource=listbox(26,159,329,34);mergedSource->add("Merged slide");mergedSource->value(1);bind(mergedSource,"merged");
        outopen=btn(26,210,64,"Open","out_open");outwhole=btn(98,210,140,"Add whole slide","out_whole");
        outregion=btn(26,249,212,"Add segmented region","out_region");style(outwhole,blue());style(outregion,teal());
        reset=btn(26,310,170,"Reset output layout","out_reset");
        outobjects=listbox(378,159,287,163);bind(outobjects,"out_object");outremove=btn(378,336,166,"Remove placement","out_remove");
        outprev=new Canvas(690,159,398,210,b,3);
        outalign=btn(690,382,181,"Open manipulation","out_align");style(outalign,teal());
        generate=btn(882,382,206,"Generate slide","export");style(generate,blue());
        format=new Fl_Choice(88,510,91,28,"Format");format->add("EP|TIFF|DICOM");format->value(0);bind(format,"format");
        bits=spin(276,510,58,"Bits",5,8,8);loss=spin(476,510,62,"Error (%)",0,15,5);jxl=spin(664,510,63,"JXL distance",1,15,4);
        facts=btn(820,510,268,"Select verified DICOM details","facts");facts->deactivate();
        output->resizable(outprev);output->end();
        rule=new Fl_Group(16,104,1098,495);
        caption(32,130,350,"Mapping rules");
        const char* rules[]={"Open a slide to define crop regions for the current frame. Originals are never changed.",
          "Shift+Z records the outline; Shift+S saves it. Shift+A steps back, Shift+R clears, and Shift+D subtracts.",
          "Right-click a saved crop to delete it and its placements in the current frame.",
          "In Open manipulation, drag to move; drag the center dot in an arc to rotate.",
          "Right-drag horizontally to resize. Double-click a placement to flip horizontally or vertically.",
          "Scroll to zoom, drag empty space to pan, or choose Auto fit. Opacity is for alignment only.",
          "Save a new .epmap project to keep the mapping. Generate a new slide from the Output tab."};
        for(int i=0;i<7;i++){auto*w=new Fl_Box(32,175+42*i,1050,35,rules[i]);w->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE|FL_ALIGN_WRAP);}
        rule->end();body->end();
        status=new Fl_Box(21,623,917,35);status->align(FL_ALIGN_LEFT|FL_ALIGN_INSIDE|FL_ALIGN_CLIP);status->labelcolor(muted());
        cancel=btn(945,625,144,"Cancel export","cancel");cancel->hide();win.end();win.resizable(body);
        win.size_range(1130,680,2200,1400);win.user_data(this);win.callback([](Fl_Widget*,void*ptr){auto&u=*static_cast<UI*>(ptr);
            if(u.exporting){u.say("Finish or cancel the current export.");return;}
            if(u.b.get("dirty")=="1"&&fl_choice("Close without saving this mapping?","Stay","Close",nullptr)!=1)return;u.win.hide();},this);refresh();
    }
    static void action(Fl_Widget*w,void*cmd){static_cast<UI*>(w->window()->user_data())->on((const char*)cmd);}
    void bind(Fl_Widget*w,const char*c){w->callback(action,(void*)c);}
    Fl_Button* btn(int x,int y,int w,const char*l,const char*c){auto*p=new Fl_Button(x,y,w,29,l);p->labelsize(13);bind(p,c);return p;}
    Fl_Spinner* spin(int x,int y,int w,const char*l,int lo,int hi,int v){auto*s=new Fl_Spinner(x,y,w,28,l);s->range(lo,hi);s->step(1);s->value(v);return s;}
    void say(const string&s){status->copy_label(s.c_str());status->tooltip(status->label());}
    bool cmd(const char*c,const string&s="",double a=0,double d=0){bool ok=b.send(c,s,a,d);if(!ok)say(b.error);return ok;}
    bool meta(){if(!layer->visible())return true;return cmd("distance",dist->value());}
    void select(int t){if(exporting||!meta())return;if(t>0&&t<OUT){if(!cmd("frame","",t-1))return;}
        tab=t;refresh();reveal();}
    void reveal(){auto*w=tabs[tab];int d=w->x()-strip->x();int delta=d<0?d:d+w->w()>strip->w()?d+w->w()-strip->w():0;
        if(delta)strip->scroll_to(std::max(0,strip->xposition()+delta),0);}
    void tabbar(){titles=lines(b.get("titles"));int x=strip->x()+2-strip->xposition();
        for(int i=0;i<23;i++){auto*w=tabs[i];if(i>int(titles.size())&&i<OUT){w->hide();continue;}
            string s=i==0?"Input":i==OUT?"Output":i==RULE?"Rule":titles[i-1];
            w->copy_tooltip(s.c_str());fl_font(FL_HELVETICA_BOLD,14);string shortname=s;
            if(fl_width(s.c_str())>220){while(shortname.size() && fl_width((shortname+"...").c_str())>217){
                size_t k=shortname.size()-1;while(k&&((unsigned char)shortname[k]&192)==128)--k;shortname.resize(k);}shortname+="...";}
            w->copy_label(shortname.c_str());int width=std::max(76,(int)fl_width(shortname.c_str())+26);
            w->resize(x,strip->y()+3,width,31);w->labelfont(FL_HELVETICA_BOLD);w->color(i==tab?teal():fl_rgb_color(238,244,241));w->labelcolor(i==tab?FL_WHITE:muted());w->show();x+=width+4;
        }strip->redraw();}
    void refresh(){
        int src,frames,planes,bo,ao;double angle,scale;std::istringstream st(b.get("state"));st>>src>>fi>>oi>>frames>>planes>>angle>>scale>>bo>>ao;
        tabbar();for(auto*g:{input,layer,output,rule})g->hide();
        if(tab==0){input->show();fill(inputs,lines(b.get("sources")),src);}
        else if(tab==RULE)rule->show();
        else if(tab==OUT){
            output->show();int valid=0,selected=-1,plane=0,count=0;
            std::istringstream os(b.get("out_state"));os>>valid>>selected>>plane>>count;
            enable(mergedSource,valid==1);
            fill(outobjects,valid==1?lines(b.get("out_objects")):std::vector<string>{},selected);
            for(auto*w:{outwhole,outopen,outregion})enable(w,valid==1);
            enable(reset,valid!=0);enable(outalign,count>0);enable(generate,count>0);enable(outremove,selected>=0);
            if(valid<0)say("Merged slide bounds changed. Reset the output layout before placing regions again.");
            outprev->redraw();
        }
        else{
            layer->show();name->value(b.get("name_value").c_str());auto v=b.get("distance_value");dist->value(v.empty()?"NA":v.c_str());
            auto vrows=lines(b.get("planes"));if(row<0||row>=(int)vrows.size())row=vrows.empty()?-1:0;
            fill(sources,vrows,row);if(row>=0)b.send("row","",row);
            auto placed=lines(b.get("objects"));fill(objects,placed,oi);
            enable(open,row>=0);enable(whole,row>=0);enable(region,row>=0);enable(remove,oi>=0);
            enable(add,frames<20);enable(del,fi>0);enable(left,fi>1);enable(right,fi>0&&fi+1<frames);
            enable(manip,!placed.empty()||fi>0);preview->redraw();
        }
        win.redraw();
    }
    void popup(int kind){
        bool isout=tab==OUT;if(!cmd(isout?"out_open":"open",kind==1?"source":"align"))return;
        double bo=3,ao=5;int si,frame,index,n,z;double angle,scale;
        std::istringstream st(b.get("state"));st>>si>>frame>>index>>n>>z>>angle>>scale>>bo>>ao;
        string title=isout?(kind==1?"Merged slide":"Output | Open manipulation"):(kind==1?sources->text(row+1):titles[fi]+" | Open manipulation");
        Popup p(b,kind,title,!isout&&kind==2&&fi>0,bo,ao,isout);p.win.show();p.stage->take_focus();
        while(p.win.shown())Fl::wait();
        cmd("close_view");refresh();
    }
    void select_region(){
        auto rs=lines(b.get(tab==OUT?"out_regions":"regions"));if(rs.empty()){say("Open the slide and save a crop with Shift+S first.");return;}
        Fl_Double_Window dialog(350,300,"Add segmented region");auto*ls=listbox(14,16,322,214);fill(ls,rs,0);
        Fl_Button no(18,250,88,29,"Cancel"),ok(199,250,133,29,"Add region");bool accept=false;
        no.callback([](Fl_Widget*w,void*){w->window()->hide();});ok.callback([](Fl_Widget*w,void*p){*static_cast<bool*>(p)=true;w->window()->hide();},&accept);
        dialog.end();dialog.set_modal();dialog.show();while(dialog.shown())Fl::wait();if(accept&&ls->value())cmd(tab==OUT?"out_region_place":"region_place","",ls->value()-1);
    }
    static void poll(void*p){auto&u=*static_cast<UI*>(p);if(u.b.get("busy")=="1"){Fl::repeat_timeout(.25,poll,p);return;}
        u.exporting=false;u.body->activate();u.strip->activate();u.cancel->hide();u.say(u.b.get("status"));u.refresh();}
    void on(string c){
        if(c=="cancel"){cmd("cancel");return;}
        if(c=="name"){if(cmd("name",name->value()))tabbar();return;}
        if(c=="distance"){meta();return;}
        if(c=="srgb"){cmd("srgb","",srgb->value());return;}
        if(c=="source"){row=sources->value()-1;if(row>=0)cmd("row","",row);if(Fl::event_clicks()&&row>=0){Fl::event_clicks(0);popup(1);}return;}
        if(c=="object"){oi=objects->value()-1;cmd("object","",oi);enable(remove,oi>=0);return;}
        if(c=="open"||c=="align"){if(meta())popup(c=="open"?1:2);return;}
        if(c=="merged"){if(Fl::event_clicks()&&outopen->active()){Fl::event_clicks(0);popup(1);}return;}
        if(c=="out_object"){cmd("out_object","",outobjects->value()-1);refresh();return;}
        if(c=="out_open"||c=="out_align"){popup(c=="out_open"?1:2);return;}
        if(c=="out_region"){select_region();refresh();return;}
        if(c=="out_whole"){cmd("out_whole");refresh();return;}
        if(c=="out_remove"){if(fl_choice("Remove this output placement from all frames?","Keep","Remove",nullptr)==1)cmd("out_remove");refresh();return;}
        if(c=="out_reset"){if(fl_choice("Clear output placements and crops? The basal layer and frames will not change.","Keep","Reset layout",nullptr)==1)cmd("out_reset");refresh();return;}
        if(c=="format"){for(auto*s:{bits,loss,jxl})enable(s,format->value()==0);enable(facts,format->value()==2);return;}
        if(!meta())return;std::vector<string> paths;
        if(c=="whole")cmd("whole");
        else if(c=="region")select_region();
        else if(c=="addframe"){if(cmd("addframe"))tab=fi+2;}
        else if(c=="deleteframe"){if(fl_choice("Delete this frame, its regions and placements?","Keep frame","Delete",nullptr)==1 && cmd("deleteframe"))tab=fi;}
        else if(c=="left"||c=="right"){int d=c=="left"?-1:1;if(cmd("order","",d))tab=fi+d+1;}
        else if(c=="remove"){if(fl_choice("Remove this placement?","Keep","Remove",nullptr)==1)cmd("remove");}
        else if(c=="input"){if(choose("Open whole slides",Fl_Native_File_Chooser::BROWSE_MULTI_FILE,"Whole slides\t*.{ep,ndpi,svs,mrxs,bif,tiff,tif,scn,svslide,isyntax}",paths))
            for(auto&p:paths)if(!cmd("input",p))break;}
        else if(c=="load"||c=="save"){
            if(c=="load"&&b.get("dirty")=="1"&&fl_choice("Discard unsaved mapping changes?","Keep editing","Load",nullptr)!=1)return;
            if(choose(c=="load"?"Load mapping project":"Save new mapping project",c=="load"?Fl_Native_File_Chooser::BROWSE_FILE:Fl_Native_File_Chooser::BROWSE_SAVE_FILE,
                "Mapping project\t*.epmap",paths,c=="save"?"mapping.epmap":nullptr)&&cmd(c.c_str(),paths[0])){row=-1;say(c=="load"?"Project loaded.":"Project saved.");}}
        else if(c=="facts"){if(choose("Verified per-section DICOM facts",Fl_Native_File_Chooser::BROWSE_FILE,"JSON\t*.json",paths)&&cmd("facts",paths[0]))say("DICOM facts selected.");}
        else if(c=="export"){
            const char* exts[]={"ep","tiff","dcm"};string ext=string(".")+exts[format->value()],n="mapped"+ext;
            if(!choose("Generate new whole slide",Fl_Native_File_Chooser::BROWSE_SAVE_FILE,("*"+ext).c_str(),paths,n.c_str()))return;
            if(paths[0].size()<=ext.size()||paths[0].substr(paths[0].size()-ext.size())!=ext){say("Use the selected format's extension: "+ext);return;}
            if(cmd("settings",std::to_string(int(jxl->value())),bits->value(),loss->value())&&cmd("export",paths[0])){
                exporting=true;body->deactivate();strip->deactivate();cancel->show();say("Exporting...");Fl::add_timeout(.25,poll,this);}return;
        }
        refresh();reveal();
    }
};
extern "C" API int manipulator_show(Call c,Paint p,int smoke){
    Fl::scheme("gtk+");UI u(c,p);u.win.show();Fl::check();
    if(smoke){u.select(1);u.on("addframe");int rc=u.tab==2&&u.titles.size()==2?0:1;u.win.hide();return rc;}
    return Fl::run();}

// Packaged acceptance uses a synthetic WSI and the same native handlers as each popup.
extern "C" API int manipulator_check(Call c,Paint p,const char* save_path){
    Fl::scheme("gtk+");UI u(c,p);u.win.show();Fl::check();
    if(u.tab!=0||!u.input->visible())return 40;
    u.select(1);u.on("whole");u.on("addframe");
    if(u.fi!=1||u.left->active()||u.right->active())return 41;
    u.name->value("IHC");u.name->do_callback();u.dist->value("0.25");u.dist->do_callback();
    if(u.titles[1]!="Layer 1 (IHC)")return 42;
    u.on("addframe");u.on("left");u.on("right");u.select(2);
    if(u.titles.size()!=3||u.fi!=1||!u.right->active()||u.titles[1]!="Layer 1 (IHC)")return 43;
    if(!u.cmd("open","source"))return 44;
    {
        Popup v(u.b,1,"Crop check",false,0,0);v.win.show();Fl::check();
        auto ev=[&](int e,int x,int y,int key=0,int state=0){
            Fl::e_x=v.stage->x()+x;Fl::e_y=v.stage->y()+y;Fl::e_keysym=key;Fl::e_state=state;return v.stage->handle(e);};
        auto square=[&](int x,int y){
            ev(FL_MOVE,x,y);ev(FL_KEYDOWN,x,y,'z',FL_SHIFT);
            ev(FL_MOVE,x+75,y);ev(FL_MOVE,x+75,y+65);ev(FL_MOVE,x,y+65);ev(FL_KEYDOWN,x,y,'s',FL_SHIFT);};
        square(340,240);square(534,292);
        if(lines(u.b.get("regions")).size()!=2)return 45;
        if(!u.cmd("region_place","",1))return 46;
        ev(FL_PUSH,555,310,FL_Button+3);
        if(!v.actions||!v.actions->shown()||!v.is_delete)return 53;
        v.first->do_callback();if(!v.confirm||lines(u.b.get("regions")).size()!=2)return 54;
        v.first->do_callback();
        if(lines(u.b.get("regions")).size()!=1||!u.b.get("objects").empty())return 47;
        v.win.hide();
    }
    u.cmd("close_view");u.cmd("region_place","",0);u.refresh();
    if(!u.cmd("open","align"))return 48;
    {
        Popup v(u.b,2,"Alignment check",true,3,5);v.win.show();Fl::check();
        if(!v.base||v.base->value()!=.3||v.active->value()!=.5)return 49;
        v.base->value(.4);v.active->value(.7);v.active->do_callback();
        auto mouse=[&](int e,int x,int y,int button){Fl::e_x=v.stage->x()+x;Fl::e_y=v.stage->y()+y;Fl::e_keysym=FL_Button+button;
            Fl::e_clicks=0;Fl::e_state=0;return v.stage->handle(e);};
        // Both windows have the same dimensions and the basal WSI fixes alignment bounds.
        mouse(FL_PUSH,378,273,1);mouse(FL_DRAG,398,273,1);mouse(FL_DRAG,378,294,1);mouse(FL_RELEASE,378,294,1);
        mouse(FL_PUSH,378,273,3);mouse(FL_DRAG,410,273,3);mouse(FL_RELEASE,410,273,3);
        for(int option=0;option<2;option++){
            Fl::e_x=v.stage->x()+390;Fl::e_y=v.stage->y()+275;Fl::e_keysym=FL_Button+1;Fl::e_clicks=1;
            v.stage->handle(FL_PUSH);if(!v.actions||!v.actions->shown()||v.is_delete)return 50;
            (option?v.second:v.first)->do_callback();if(v.actions->shown())return 55;
        }
        mouse(FL_PUSH,390,275,1);mouse(FL_DRAG,404,292,1);mouse(FL_RELEASE,404,292,1);
        v.call("autofit");v.win.hide();
    }
    u.cmd("close_view");u.select(UI::OUT);if(!u.output->visible()||u.outprev->handle(FL_PUSH))return 51;
    if(!u.srgb->value()||u.generate->active()||!u.outopen->active())return 56;
    if(u.titles.size()!=3||u.mergedSource->size()!=1||string(u.mergedSource->text(1))!="Merged slide")return 68;
    u.on("out_whole");if(!u.generate->active()||!u.outalign->active()||u.outobjects->size()!=1)return 57;
    if(!u.cmd("out_open","source"))return 58;
    {
        Popup v(u.b,1,"Merged slide",false,0,0,true);v.win.show();Fl::check();
        v.call("viewport","",v.stage->w(),v.stage->h());
        if(!v.plane||v.plane->size()!=4||!v.key(FL_Page_Up,true)||v.plane->value()!=1)return 59;
        if(u.mergedSource->size()!=1||string(u.mergedSource->text(1))!="Merged slide")return 69;
        if(!v.key(FL_Page_Down,true)||v.plane->value()!=0)return 60;
        v.call("point","",310,220);v.key('z',true);v.call("point","",430,220);v.call("point","",430,350);
        v.call("point","",310,350);v.key('s',true);v.win.hide();
    }
    u.cmd("close_view");if(lines(u.b.get("out_regions")).size()!=1||!u.cmd("out_region_place","",0))return 61;
    u.refresh();if(u.outobjects->size()!=2)return 62;
    if(!u.cmd("save",save_path))return 52;
    u.win.hide();return 0;}
