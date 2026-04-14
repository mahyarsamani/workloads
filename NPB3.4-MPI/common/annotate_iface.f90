module annotate_iface
  use, intrinsic :: iso_c_binding, only: c_int64_t
  implicit none
  interface
    subroutine annotate_synchronize(expected) bind(C, name="annotate_synchronize_")
      import :: c_int64_t
      integer(c_int64_t), value :: expected
    end subroutine
  end interface
end module annotate_iface