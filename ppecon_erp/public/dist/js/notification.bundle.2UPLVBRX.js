(()=>{function _(r,a,p){let s="";if(p){let o=new Date;o.setTime(o.getTime()+p*24*60*60*1e3),s="; expires="+o.toUTCString()}document.cookie=r+"="+(a||"")+s+"; path=/"}function N(r){let a=r+"=",p=document.cookie.split(";");for(let s=0;s<p.length;s++){let o=p[s];for(;o.charAt(0)===" ";)o=o.substring(1,o.length);if(o.indexOf(a)===0)return o.substring(a.length,o.length)}return null}function q(r){let a=$("<div></div>"),p=new Audio("/files/pristine-609.mp3"),s=$(`
        <div class="modal fade" id="quick-chat-popup" tabindex="-1" role="dialog" aria-labelledby="exampleModalCenterTitle" aria-hidden="true">
            <div class="modal-dialog" role="document" style="bottom: 60px; position: absolute; right: 20px; max-width: 400px; width: 100%;">
                <div class="modal-content" id="main-quick-chat-container" style="border-radius: 10px; box-shadow: 0px 4px 8px rgba(0, 0, 0, 0.1);">
                    <div class="modal-header" style="background-color: #f1f3f4; color: black; padding: 10px;">
                        <h5 class="modal-title" style="font-weight: bold; color: #343a40;">\u{1F514} Notifications</h5>
                        <button type="button" class="close" data-dismiss="modal" aria-label="Close">
                            <span aria-hidden="true">&times;</span>
                        </button>
                    </div>
                    <div class="modal-body" id="notification-list" style="max-height: 400px; overflow-y: auto; padding: 0;">
                        <p style="padding: 15px; text-align: center; color: #777;">No notifications available.</p>
                    </div>
                </div>
            </div>
        </div>
    `),o=$('<button id="quick_chat_button" data-toggle="modal" data-target="#quick-chat-popup" type="button" class="btn btn-primary btn-rounded btn-icon"><i class="fa fa-bell"></i></button>'),d=$('<span class="count">0</span>');d.css({position:"absolute",top:"-5px",right:"-5px","background-color":"red",color:"white","border-radius":"50%",padding:"2px 5px","font-size":"12px","min-width":"20px","text-align":"center"}),o.css({position:"fixed",bottom:"20px",right:"100px","border-radius":"50%",width:"50px",height:"50px","align-items":"center","justify-content":"center","z-index":"9999","box-shadow":"0px 0px 10px rgba(0, 0, 0, 0.2)","background-color":"#007bff",color:"white","font-size":"20px"}),o.append(d),a.append(s),a.append(o),$(r).append(a);let x=`
        /* Mobile Screens (up to 768px) */
        @media (max-width: 768px) {
            #quick_chat_button {
                bottom: 15px !important;
                right: 30px !important;  /* Adjusted for mobile */
                width: 40px !important;
                height: 40px !important;
                font-size: 18px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 50px !important;
                right: 20px !important;  /* Align the modal with the button */
                max-width: 300px !important;
                width: 100% !important;
            }
        }

        /* Tablet Screens (769px to 1024px) */
        @media (min-width: 769px) and (max-width: 1024px) {
            #quick_chat_button {
                bottom: 20px !important;
                right: 50px !important;  /* Adjusted for tablet */
                width: 45px !important;
                height: 45px !important;
                font-size: 19px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 60px !important;
                right: 35px !important;  /* Align the modal with the button */
                max-width: 350px !important;
                width: 100% !important;
            }
        }

        /* Laptop and Larger Screens (1025px and up) */
        @media (min-width: 1025px) {
            #quick_chat_button {
                bottom: 20px !important;
                right: 100px !important;  /* Adjusted for laptop/desktop */
                width: 50px !important;
                height: 50px !important;
                font-size: 20px !important;
            }

            #quick-chat-popup .modal-dialog {
                bottom: 60px !important;
                right: 20px !important;  /* Align the modal with the button */
                max-width: 400px !important;
                width: 100% !important;
            }
        }
    `;$("<style>").text(x).appendTo("head");let m=JSON.parse(N("previousNotificationIds"))||[];l(d),setInterval(()=>l(d),1e4),k();function g(){console.log("Playing sound from:",p.src),p.play().catch(function(n){console.error("Audio playback failed:",n)})}function b(n){let i=$(`
            <div class="toast-notification" style="
                position: fixed;
                top: -50px;
                left: 50%;
                transform: translateX(-50%);
                background-color: #007bff;
                color: white;
                padding: 15px 20px;
                border-radius: 8px;
                box-shadow: 0px 4px 10px rgba(0, 0, 0, 0.1);
                font-size: 16px;
                z-index: 10000;
                opacity: 0;
                transition: all 0.5s ease;
            ">
                \u{1F389} ${n}
            </div>
        `);$("body").append(i),setTimeout(()=>{i.css({top:"20px",opacity:"1"})},100),setTimeout(()=>{i.css({top:"-50px",opacity:"0"}),setTimeout(()=>i.remove(),500)},4e3)}function l(n,i=!1){frappe.call({method:"ppecon_erp.notification.get_unread_notifications",callback:function(t){let c=t.message,u=$("#notification-list");if(u.empty(),c&&c.length>0){let f=c.map(e=>e.name);f.filter(e=>!m.includes(e)).length>0&&!i&&(g(),b("New Notification! Something exciting just happened!")),m=f,_("previousNotificationIds",JSON.stringify(m),1),n.text(c.length),c.forEach(e=>{let v=w(new Date(e.creation)),h=$(`
                            <div class="notification-item" style="display: flex; align-items: center; padding: 12px; border-bottom: 1px solid #ddd; cursor: pointer;">
                                <div class="notification-content" style="flex-grow: 1; overflow: hidden;">
                                    <strong style="font-size: 14px; color: #007bff;">${e.subject||"Notification"}</strong>
                                    <p style="font-size: 12px; color: #555; margin: 0;">${e.email_content||"No content available."}</p>
                                    <span class="notification-time" style="font-size: 11px; color: #888;">${v}</span>
                                </div>
                            </div>
                        `);h.on("click",async function(){await y(e.name),l(n,!0),window.location.href=`/app/${e.document_type.toLowerCase()}/${e.document_name}`}),u.append(h)})}else u.append('<p style="padding: 15px; text-align: center; color: #777;">No notifications available.</p>')}})}function w(n){let i=Math.floor((new Date-n)/1e3),t=Math.floor(i/31536e3);return t>1?t+" years ago":(t=Math.floor(i/2592e3),t>1?t+" months ago":(t=Math.floor(i/86400),t>1?t+" days ago":(t=Math.floor(i/3600),t>1?t+" hours ago":(t=Math.floor(i/60),t>1?t+" minutes ago":Math.floor(i)+" seconds ago"))))}function y(n){return frappe.call({method:"ppecon_erp.notification.mark_notification_as_read",args:{notification_name:n},callback:function(i){l($(".count"),!0)}})}function k(){window.addEventListener("quick_chat_child__close_dialog",function(n){$("#quick-chat-popup").modal("hide")},!1)}}q(document.querySelector(".main-section"));})();
//# sourceMappingURL=notification.bundle.2UPLVBRX.js.map
